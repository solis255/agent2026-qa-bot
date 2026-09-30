"""Milestone 9C Web contract and same-origin account-flow acceptance."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from netpilot.agent import AgentResult, AgentStatus
from netpilot.config import Settings
from netpilot.main import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DemoAgent:
    def run(self, message: str, *, history=(), task_state=None) -> AgentResult:
        del history, task_state
        return AgentResult(
            answer=f"诊断完成：{message}",
            status=AgentStatus.COMPLETED,
            tool_rounds=0,
        )


def test_web_exposes_auth_forms_account_menu_and_password_dialog() -> None:
    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for element_id in (
        "auth-gate", "auth-login-tab", "auth-register-tab", "auth-form",
        "auth-username", "auth-nickname", "auth-password", "auth-confirm",
        "account-menu", "account-name", "my-history", "logout-button",
        "change-password-open", "password-dialog", "password-form",
        "old-password", "new-password", "confirm-new-password",
        "my-history-card",
    ):
        assert f'id="{element_id}"' in html
    assert '<main class="workspace" id="workspace" hidden>' in html
    assert "我的诊断历史" in html
    assert "学校统一身份认证密码" in html
    assert 'type="password"' in html


def test_web_uses_cookie_auth_without_browser_token_storage() -> None:
    javascript = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    for endpoint in (
        "/api/auth/me", "/api/auth/register", "/api/auth/login",
        "/api/auth/logout", "/api/auth/change-password",
    ):
        assert endpoint in javascript
    assert javascript.count('credentials: "same-origin"') >= 3
    assert 'const user = await requestJSON("/api/auth/me")' in javascript
    assert "await enterAuthenticated(user)" in javascript
    assert "showAuthGate(" in javascript
    assert "state.authEpoch" in javascript
    assert "elements.conversation.replaceChildren()" in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert "innerHTML" not in javascript


def test_web_auth_runtime_state_flow() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    script = PROJECT_ROOT / "tests" / "web_auth_runtime.cjs"
    result = subprocess.run(
        [node, str(script)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_same_origin_web_account_flow_and_personal_history(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            tju_api_key="web-flow-test-key",
            tool_mode="mock",
            rag_enabled=False,
            diagnosis_history_enabled=True,
            diagnosis_db_path=tmp_path / "netpilot.db",
        )
    )
    app.state.agent = DemoAgent()
    with TestClient(app) as alice, TestClient(app) as bob:
        assert alice.get("/").status_code == 200
        assert alice.get("/app.js").status_code == 200
        assert alice.get("/style.css").status_code == 200
        assert alice.get("/api/auth/me").status_code == 401
        registered = alice.post(
            "/api/auth/register",
            json={"username": "web_alice", "password": "test-password-123", "nickname": "演示 A"},
        )
        assert registered.status_code == 201
        assert alice.get("/api/auth/me").json()["nickname"] == "演示 A"
        session = alice.post("/api/session").json()["session_id"]
        chat = alice.post(
            "/api/chat", json={"session_id": session, "message": "DNS 故障"}
        )
        assert chat.status_code == 200
        record_id = chat.json()["record_id"]
        assert alice.get("/api/diagnoses").json()["items"][0]["record_id"] == record_id

        changed = alice.post(
            "/api/auth/change-password",
            json={"old_password": "test-password-123", "new_password": "new-password-456"},
        )
        assert changed.status_code == 204
        assert alice.get("/api/auth/me").status_code == 200
        assert alice.post("/api/auth/logout").status_code == 204
        assert alice.get("/api/auth/me").status_code == 401
        assert alice.get("/api/diagnoses").status_code == 401

        assert bob.post(
            "/api/auth/register",
            json={"username": "web_bob", "password": "test-password-123"},
        ).status_code == 201
        assert bob.get("/api/diagnoses").json()["items"] == []
        assert bob.get(f"/api/diagnoses/{record_id}").status_code == 404

        assert alice.post(
            "/api/auth/login",
            json={"username": "web_alice", "password": "test-password-123"},
        ).status_code == 401
        assert alice.post(
            "/api/auth/login",
            json={"username": "web_alice", "password": "new-password-456"},
        ).status_code == 200
        assert alice.get("/api/diagnoses").json()["items"][0]["record_id"] == record_id
