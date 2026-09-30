"""Milestone 9B authorization and legacy diagnosis migration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import register_test_user
from netpilot.agent import AgentResult, AgentStatus
from netpilot.api.presenters import present_chat
from netpilot.config import Settings
from netpilot.history import (
    DiagnosisRecordNotFoundError,
    DiagnosisStorageError,
    SQLiteDiagnosisRepository,
)
from netpilot.main import create_app


class OwnershipAgent:
    def run(self, message: str, *, history=(), task_state=None) -> AgentResult:
        del history, task_state
        return AgentResult(
            answer=f"诊断完成：{message}",
            status=AgentStatus.COMPLETED,
            tool_rounds=0,
        )


def _app(database: Path):
    app = create_app(
        Settings(
            _env_file=None,
            tju_api_key="ownership-test-key",
            tool_mode="mock",
            rag_enabled=False,
            diagnosis_history_enabled=True,
            diagnosis_db_path=database,
        )
    )
    app.state.agent = OwnershipAgent()
    return app


def test_protected_resources_require_login(tmp_path: Path) -> None:
    app = _app(tmp_path / "netpilot.db")
    unknown = uuid4()
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        for path in (
            "/api/diagnoses",
            f"/api/diagnoses/{unknown}",
            f"/api/diagnoses/{unknown}/report",
            f"/api/diagnoses/{unknown}/export?format=json",
        ):
            assert client.get(path).status_code == 401
        assert client.post("/api/session").status_code == 401
        for path in ("/api/chat", "/api/chat/stream"):
            assert client.post(
                path, json={"session_id": str(unknown), "message": "测试"}
            ).status_code == 401


def test_two_users_cannot_use_or_read_each_others_resources(tmp_path: Path) -> None:
    app = _app(tmp_path / "netpilot.db")
    with TestClient(app) as alice, TestClient(app) as bob:
        alice_id = register_test_user(alice)
        bob_id = register_test_user(bob)
        alice_session = alice.post("/api/session").json()["session_id"]
        bob_session = bob.post("/api/session").json()["session_id"]

        for path in ("/api/chat", "/api/chat/stream"):
            denied = bob.post(
                path, json={"session_id": alice_session, "message": "借用会话"}
            )
            assert denied.status_code == 404
        assert not app.state.sessions.get(UUID(alice_session), alice_id).busy

        alice_chat = alice.post(
            "/api/chat", json={"session_id": alice_session, "message": "A 的 DNS"}
        )
        bob_chat = bob.post(
            "/api/chat", json={"session_id": bob_session, "message": "B 的 SSH"}
        )
        assert alice_chat.status_code == bob_chat.status_code == 200
        alice_record = alice_chat.json()["record_id"]
        bob_record = bob_chat.json()["record_id"]

        alice_list = alice.get("/api/diagnoses").json()["items"]
        bob_list = bob.get("/api/diagnoses").json()["items"]
        assert [item["record_id"] for item in alice_list] == [alice_record]
        assert [item["record_id"] for item in bob_list] == [bob_record]
        assert alice.get(f"/api/diagnoses/{alice_record}").json()["user_id"] == str(alice_id)
        assert bob.get(f"/api/diagnoses/{bob_record}").json()["user_id"] == str(bob_id)
        assert bob.get(f"/api/diagnoses?session_id={alice_session}").json()["items"] == []

        for client, other_record in ((alice, bob_record), (bob, alice_record)):
            for path in (
                f"/api/diagnoses/{other_record}",
                f"/api/diagnoses/{other_record}/report",
                f"/api/diagnoses/{other_record}/export?format=markdown",
                f"/api/diagnoses/{other_record}/export?format=json",
            ):
                assert client.get(path).status_code == 404
        assert alice.get(f"/api/diagnoses/{alice_record}/report").status_code == 200
        assert alice.get(f"/api/diagnoses/{alice_record}/export?format=json").status_code == 200


def test_legacy_history_migration_preserves_but_hides_old_records(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    seed = SQLiteDiagnosisRepository(tmp_path / "seed.db").save(
        uuid4(), "旧问题", present_chat(uuid4(), OwnershipAgent().run("旧问题"))
    )
    legacy_id = str(seed.record_id)
    legacy_session = str(seed.session_id)
    legacy_snapshot = seed.model_dump_json(exclude={"user_id"})
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE netpilot_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO netpilot_metadata(key, value) VALUES ('schema_version', '1');
            CREATE TABLE diagnosis_records (
                record_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL,
                session_id TEXT NOT NULL, created_at TEXT NOT NULL,
                user_message TEXT NOT NULL, answer_preview TEXT NOT NULL,
                status TEXT NOT NULL, primary_issue TEXT NOT NULL,
                confidence TEXT NOT NULL, snapshot_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """INSERT INTO diagnosis_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                legacy_id, 1, legacy_session, "2026-01-01T00:00:00+00:00",
                "旧问题", seed.answer, "completed", seed.diagnosis.primary_issue,
                seed.diagnosis.confidence, legacy_snapshot,
            ),
        )

    repository = SQLiteDiagnosisRepository(database)
    owner = uuid4()
    assert repository.count(owner) == 0
    assert repository.list(owner).items == []
    with pytest.raises(DiagnosisRecordNotFoundError):
        repository.get(owner, UUID(legacy_id))
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT user_id, user_message, snapshot_json FROM diagnosis_records WHERE record_id = ?",
            (legacy_id,),
        ).fetchone()
        version = connection.execute(
            "SELECT value FROM netpilot_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
    assert row == (None, "旧问题", legacy_snapshot)
    assert version == "2"

    app = _app(database)
    with TestClient(app) as client:
        user_id = register_test_user(client)
        session_id = client.post("/api/session").json()["session_id"]
        chat = client.post(
            "/api/chat", json={"session_id": session_id, "message": "新问题"}
        )
        assert chat.status_code == 200
        new_id = chat.json()["record_id"]
        assert client.get("/api/diagnoses").json()["items"][0]["record_id"] == new_id
        assert client.get(f"/api/diagnoses/{legacy_id}").status_code == 404

    reopened = SQLiteDiagnosisRepository(database)
    assert reopened.get(user_id, UUID(new_id)).user_id == user_id
    assert reopened.count(user_id) == 1
    capped = SQLiteDiagnosisRepository(database, max_records=1)
    capped.save(user_id, "另一个新问题", present_chat(uuid4(), OwnershipAgent().run("新问题")))
    assert capped.count(user_id) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM diagnosis_records WHERE record_id = ? AND user_id IS NULL",
            (legacy_id,),
        ).fetchone()[0] == 1


def test_unsupported_history_version_fails_without_rewriting_data(tmp_path: Path) -> None:
    database = tmp_path / "future.db"
    SQLiteDiagnosisRepository(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE netpilot_metadata SET value = '99' WHERE key = 'schema_version'"
        )
    with pytest.raises(DiagnosisStorageError):
        SQLiteDiagnosisRepository(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM netpilot_metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "99"
