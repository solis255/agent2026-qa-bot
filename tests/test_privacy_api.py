import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient

from conftest import register_test_user
from target_helpers import local_app
from test_remediation_api import setup_plan
from netpilot.agent import AgentResult, AgentStatus


def test_case2_note_is_accepted_redacted_persisted_and_exported(tmp_path, caplog):
    app, _ = local_app(tmp_path)
    with TestClient(app) as client:
        owner, sid, plan = setup_plan(client)
        chat = client.post("/api/chat", json={"session_id": sid, "message": "网页打不开，请分析快照"})
        assert chat.status_code == 200, chat.text
        record_id = chat.json()["record_id"]
        result = client.patch(f'/api/session/remediation-plan/steps/{plan["steps"][0]["step_id"]}',
            json={"session_id": sid, "action": "complete", "outcome": "no_change",
                  "user_note": "我的 token=abc123，重新连接以后还是不行"})
        assert result.status_code == 200, result.text
        assert "abc123" not in result.text and "[REDACTED]" in result.text
        assert "abc123" not in app.state.sessions.task_state(UUID(sid), owner).model_dump_json()
        for format in ["json", "markdown"]:
            exported = client.get(f"/api/diagnoses/{record_id}/export", params={"format": format})
            assert exported.status_code == 200 and "abc123" not in exported.text
        with sqlite3.connect(app.state.diagnosis_repository.path) as connection:
            assert "abc123" not in str(connection.execute("SELECT snapshot_json FROM diagnosis_records").fetchall())
        assert "abc123" not in caplog.text


def test_sse_redacts_before_chunking_and_returns_safe_user_message(tmp_path):
    class Agent:
        def run(self, message, **kwargs):
            return AgentResult(answer="Authorization: Bearer crosses-chunk-boundary-secret\nDNS 172.23.0.1", status=AgentStatus.COMPLETED, tool_rounds=0)
    app, _ = local_app(tmp_path); app.state.agent = Agent()
    with TestClient(app) as client:
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        result = client.post("/api/chat/stream", json={"session_id": sid, "message": "password=user-input-secret"})
        assert result.status_code == 200
        assert "crosses-chunk-boundary-secret" not in result.text and "user-input-secret" not in result.text
        assert "[REDACTED]" in result.text and "172.23.0.1" in result.text


def test_validation_and_unexpected_errors_do_not_echo_payloads(tmp_path, caplog):
    app, _ = local_app(tmp_path)
    @app.get("/api/privacy-test-error")
    def fail():
        raise RuntimeError("unlabelled-error-secret")
    # The production static mount is a catch-all; place this test endpoint first.
    app.router.routes.insert(0, app.router.routes.pop())
    with TestClient(app) as client:
        register_test_user(client)
        result = client.post("/api/chat", json={"session_id": "invalid", "message": {"secret": "raw-body-secret"}})
        assert result.status_code == 422 and "raw-body-secret" not in result.text
        result = client.get("/api/privacy-test-error")
        assert result.status_code == 500 and "unlabelled-error-secret" not in result.text + caplog.text
        assert "request_id" in result.json()
