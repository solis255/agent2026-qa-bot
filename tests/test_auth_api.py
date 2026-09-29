"""Milestone 9A account, Cookie and server-side session acceptance tests."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netpilot.config import Settings
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.main import create_app


@pytest.fixture
def auth_client(tmp_path: Path) -> tuple[TestClient, Path]:
    database = tmp_path / "netpilot.db"
    settings = Settings(
        _env_file=None,
        diagnosis_db_path=database,
        diagnosis_history_enabled=False,
        rag_enabled=False,
    )
    return TestClient(create_app(settings)), database


def _register(client: TestClient, username: str = "Demo_User"):
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "demo-password-123",
            "nickname": "演示用户",
        },
    )


def _cookie_value(response) -> str:
    return response.cookies["netpilot_session"]


def test_register_creates_argon2id_user_and_hashed_server_session(auth_client) -> None:
    client, database = auth_client
    response = _register(client)

    assert response.status_code == 201
    assert response.json()["username"] == "demo_user"
    assert response.json()["nickname"] == "演示用户"
    assert "password" not in response.text
    token = _cookie_value(response)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=43200" in cookie
    assert "Path=/" in cookie
    assert "Secure" not in cookie

    with sqlite3.connect(database) as connection:
        user = connection.execute(
            "SELECT username, password_hash FROM users"
        ).fetchone()
        session = connection.execute(
            "SELECT token_hash, expires_at FROM auth_sessions"
        ).fetchone()
    assert user[0] == "demo_user"
    assert user[1].startswith("$argon2id$")
    assert "demo-password-123" not in user[1]
    assert session[0] == hashlib.sha256(token.encode()).hexdigest()
    assert token != session[0]
    assert datetime.fromisoformat(session[1]) > datetime.now(timezone.utc)
    assert client.get("/api/auth/me").json()["username"] == "demo_user"


def test_duplicate_case_insensitive_username_and_invalid_inputs(auth_client) -> None:
    client, _ = auth_client
    assert _register(client).status_code == 201
    assert _register(client, "DEMO_USER").status_code == 409
    for username, password in (
        ("ab", "good-password"),
        ("has space", "good-password"),
        ("valid_name", "short"),
        ("valid_name", "        "),
    ):
        response = client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        assert response.status_code == 422
        assert password not in response.text


def test_login_me_logout_and_generic_failure(auth_client) -> None:
    client, _ = auth_client
    assert client.get("/api/auth/me").status_code == 401
    first = _register(client)
    token = _cookie_value(first)
    client.cookies.clear()
    wrong_user = client.post(
        "/api/auth/login",
        json={"username": "missing", "password": "wrong-password"},
    )
    wrong_password = client.post(
        "/api/auth/login",
        json={"username": "demo_user", "password": "wrong-password"},
    )
    assert wrong_user.status_code == wrong_password.status_code == 401
    assert wrong_user.json() == wrong_password.json()
    assert client.get("/api/auth/me").status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"username": "DEMO_USER", "password": "demo-password-123"},
    )
    assert login.status_code == 200
    assert _cookie_value(login) != token
    assert login.json()["last_login_at"] is not None
    assert client.get("/api/auth/me").status_code == 200

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("netpilot_session", _cookie_value(login))
    assert client.get("/api/auth/me").status_code == 401


def test_change_password_revokes_all_old_sessions_and_issues_new_cookie(
    auth_client,
) -> None:
    client, _ = auth_client
    first = _register(client)
    old_token = _cookie_value(first)
    second = client.post(
        "/api/auth/login",
        json={"username": "demo_user", "password": "demo-password-123"},
    )
    second_token = _cookie_value(second)

    wrong = client.post(
        "/api/auth/change-password",
        json={"old_password": "incorrect", "new_password": "new-password-456"},
    )
    assert wrong.status_code == 401
    change = client.post(
        "/api/auth/change-password",
        json={"old_password": "demo-password-123", "new_password": "new-password-456"},
    )
    assert change.status_code == 204
    new_token = _cookie_value(change)
    assert new_token not in {old_token, second_token}
    assert client.get("/api/auth/me").status_code == 200
    for token in (old_token, second_token):
        probe = TestClient(client.app)
        probe.cookies.set("netpilot_session", token)
        assert probe.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    assert client.post(
        "/api/auth/login",
        json={"username": "demo_user", "password": "demo-password-123"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"username": "demo_user", "password": "new-password-456"},
    ).status_code == 200


def test_invalid_and_expired_tokens_and_active_session_limit(auth_client) -> None:
    client, database = auth_client
    first = _register(client)
    first_token = _cookie_value(first)
    client.cookies.clear()
    client.cookies.set("netpilot_session", "invalid-token")
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE auth_sessions SET expires_at = ? WHERE token_hash = ?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                hashlib.sha256(first_token.encode()).hexdigest(),
            ),
        )
    client.cookies.set("netpilot_session", first_token)
    assert client.get("/api/auth/me").status_code == 401

    # The configurable cap is enforced on later logins.
    for _ in range(7):
        assert client.post(
            "/api/auth/login",
            json={"username": "demo_user", "password": "demo-password-123"},
        ).status_code == 200
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0]
    assert count == 5


def test_secure_cookie_configuration_and_cross_origin_rejection(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        diagnosis_db_path=tmp_path / "secure.db",
        diagnosis_history_enabled=False,
        rag_enabled=False,
        auth_cookie_name="np_auth",
        auth_cookie_secure=True,
        auth_session_hours=2,
    )
    client = TestClient(create_app(settings))
    cross_origin = client.post(
        "/api/auth/register",
        headers={"Origin": "http://evil.example"},
        json={"username": "demo_user", "password": "demo-password-123"},
    )
    assert cross_origin.status_code == 403
    response = client.post(
        "/api/auth/register",
        json={"username": "demo_user", "password": "demo-password-123"},
    )
    assert response.status_code == 201
    assert "np_auth=" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "Max-Age=7200" in response.headers["set-cookie"]


def test_secure_cookie_requires_https_and_logout_uses_configured_name(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        diagnosis_db_path=tmp_path / "https-auth.db",
        diagnosis_history_enabled=False,
        rag_enabled=False,
        auth_cookie_name="np_auth",
        auth_cookie_secure=True,
    )
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as client:
        register = _register(client)
        assert register.status_code == 201
        assert client.get("/api/auth/me").status_code == 200
        logout = client.post("/api/auth/logout")
        assert logout.status_code == 204
        assert "np_auth=" in logout.headers["set-cookie"]
        assert "Max-Age=0" in logout.headers["set-cookie"]
        assert "Secure" in logout.headers["set-cookie"]
        assert "HttpOnly" in logout.headers["set-cookie"]
        assert client.get("/api/auth/me").status_code == 401


def test_auth_tables_can_be_added_to_existing_diagnosis_database(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    SQLiteDiagnosisRepository(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO diagnosis_records
                (record_id, schema_version, session_id, created_at, user_message,
                 answer_preview, status, primary_issue, confidence, snapshot_json)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222",
                datetime.now(timezone.utc).isoformat(),
                "旧问题", "旧回答", "completed", "undetermined", "low", "{}",
            ),
        )
    settings = Settings(
        _env_file=None,
        diagnosis_db_path=database,
        diagnosis_history_enabled=False,
        rag_enabled=False,
    )
    client = TestClient(create_app(settings))
    assert _register(client).status_code == 201
    assert client.get("/api/auth/me").status_code == 200
    with sqlite3.connect(database) as connection:
        old = connection.execute(
            "SELECT user_message FROM diagnosis_records WHERE record_id = ?",
            ("11111111-1111-1111-1111-111111111111",),
        ).fetchone()
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert old == ("旧问题",)
    assert {"users", "auth_sessions", "diagnosis_records"} <= tables
    # Repeated application initialization is safe and does not reset accounts.
    reopened = TestClient(create_app(settings))
    assert reopened.post(
        "/api/auth/login",
        json={"username": "demo_user", "password": "demo-password-123"},
    ).status_code == 200


def test_incompatible_existing_auth_schema_fails_without_replacing_data(
    tmp_path: Path,
) -> None:
    database = tmp_path / "broken-auth.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE users (id TEXT PRIMARY KEY, legacy_data TEXT)")
        connection.execute(
            "INSERT INTO users (id, legacy_data) VALUES (?, ?)",
            ("legacy-user", "preserve-me"),
        )
    settings = Settings(
        _env_file=None,
        diagnosis_db_path=database,
        diagnosis_history_enabled=False,
        rag_enabled=False,
    )
    client = TestClient(create_app(settings))
    assert _register(client).status_code == 503
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT legacy_data FROM users WHERE id = ?", ("legacy-user",)
        ).fetchone() == ("preserve-me",)
