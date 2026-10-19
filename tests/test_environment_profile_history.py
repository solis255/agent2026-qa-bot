import json
import sqlite3
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from conftest import register_test_user
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.reports import build_diagnosis_report, render_report_markdown, render_report_json
from reasoning_helpers import CASE_B, CASE_C, trace_app


def test_ep09_three_turn_chat_sse_history_restart_and_report(tmp_path):
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        first = client.post("/api/chat", json={"session_id":sid, "message":"我的 Windows 11 笔记本连校园 WiFi 后微信正常，但网页打不开，我没开 VPN。"})
        assert first.status_code == 200
        rid = first.json()["record_id"]
        stream = client.post("/api/chat/stream", json={"session_id":sid,"message":CASE_B})
        block = next(block for block in stream.text.split("\n\n") if "event: complete" in block)
        second = json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))["response"]
        third = client.post("/api/chat", json={"session_id":sid,"message":CASE_C}).json()
        assert second["environment_profile"] == third["environment_profile"] == first.json()["environment_profile"]
        before = client.get(f"/api/diagnoses/{rid}").json()
        patch = client.patch("/api/session/environment/user", json={"session_id":sid,"os_family":"macos"})
        assert patch.status_code == 200
        after = client.get(f"/api/diagnoses/{rid}").json()
        assert after["environment_profile"]["os_family"] == "macos"
        for field in ("turn_count","conversation_turns","tool_calls","sources","reasoning_trace","metrics","updated_at"):
            assert after[field] == before[field]
        assert client.get("/api/diagnoses").json()["items"][0]["turn_count"] == 3
    repository = SQLiteDiagnosisRepository(tmp_path / "trace.db")
    record = repository.get(owner, UUID(rid))
    assert record.turn_count == len(record.conversation_turns) == 3
    assert repository.count(owner) == 1
    assert record.environment_profile.os_family == "macos"
    assert record.environment_profile.proxy_enabled is None
    assert record.schema_version == 10
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute("SELECT value FROM netpilot_metadata WHERE key='schema_version'").fetchone()[0] == "3"
    report = build_diagnosis_report(record)
    markdown = render_report_markdown(report)
    assert "## 用户环境" in markdown and "macOS" in markdown
    assert "VPN：关闭" in markdown and "Proxy：未知" in markdown
    assert "field_sources" not in markdown
    exported = json.loads(render_report_json(report))["environment_profile"]
    assert exported["field_sources"]["os_family"] == {"source":"user", "confidence":"high"}


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_ep10_legacy_snapshots_default_to_unknown_without_inference(tmp_path, version):
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        response = client.post("/api/chat", json={"session_id":sid,"message":"我现在用 Windows，连校园 WiFi，网页打不开"}).json()
        record = app.state.diagnosis_repository.get(owner, UUID(response["record_id"]))
    payload = record.model_dump(mode="json", exclude={"environment_profile"})
    payload["schema_version"] = version
    with sqlite3.connect(tmp_path / "trace.db") as connection:
        connection.execute("UPDATE diagnosis_records SET schema_version=?, snapshot_json=? WHERE record_id=?", (version, json.dumps(payload), str(record.record_id)))
    reopened = SQLiteDiagnosisRepository(tmp_path / "trace.db")
    loaded = reopened.get(owner, record.record_id)
    assert loaded.environment_profile.os_family == loaded.environment_profile.client_mode == "unknown"
    assert loaded.environment_profile.vpn_enabled is None
    assert loaded.environment_profile.field_sources == {}
    assert loaded.conversation_turns == record.conversation_turns
    assert loaded.reasoning_trace == record.reasoning_trace
    assert "## 用户环境" in render_report_markdown(build_diagnosis_report(loaded))


def test_failed_environment_persistence_keeps_authoritative_session_unchanged(tmp_path, monkeypatch):
    from netpilot.history import DiagnosisStorageError
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        session = client.post("/api/session").json()
        def fail(*args):
            raise DiagnosisStorageError("private-storage-detail")
        monkeypatch.setattr(app.state.diagnosis_repository, "update_environment_profile", fail)
        response = client.patch("/api/session/environment/user", json={"session_id":session["session_id"],"os_family":"windows"})
        assert response.status_code == 503
        assert "private-storage-detail" not in response.text
        assert client.get(f"/api/session/{session['session_id']}").json() == session
