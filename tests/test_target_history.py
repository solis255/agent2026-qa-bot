import json
import sqlite3
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from netpilot.history import SQLiteDiagnosisRepository, DiagnosisStorageError
from netpilot.reports import build_diagnosis_report, render_report_markdown, render_report_json
from target_helpers import local_app


def test_dt12_history_report_switch_archive_and_chat_sse_match_after_restart(tmp_path):
    app,counts = local_app(tmp_path)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        host = client.post("/api/chat",json={"session_id":sid,"message":"检查 NetPilot 服务器的 DNS，调用 dns_lookup"})
        assert host.status_code == 200
        host = host.json()
        rid = host["record_id"]
        assert host["tool_calls"][0]["execution_context"] == "netpilot_host"
        patch = client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"user_client"})
        assert patch.status_code == 200
        report = client.get(f"/api/diagnoses/{rid}/report").json()
        assert "尚无当前对象" in report["conclusion"]
        assert report["tool_calls"] == []
        assert report["archived_tool_calls"][0]["target_subject"] == "netpilot_host"
        assert not report["diagnosis"]["evidence"]
        stream = client.post("/api/chat/stream",json={"session_id":sid,"message":"我的电脑 DNS 正常吗？"})
        block = next(part for part in stream.text.split("\n\n") if "event: complete" in part)
        response = json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))["response"]
        assert response["diagnostic_target"] == client.get(f"/api/session/{sid}").json()["diagnostic_target"]
        assert response["tool_calls"] == []
        assert "DNS 正常" not in response["answer"]
    repository = SQLiteDiagnosisRepository(tmp_path / "target.db")
    record = repository.get(owner,UUID(rid))
    assert record.schema_version == 10 and repository.count(owner) == 1
    assert record.turn_count == len(record.conversation_turns) == 2
    assert record.diagnostic_target.subject == "user_client"
    assert record.tool_calls[0].target_subject == "netpilot_host"  # Archive preserved.
    assert not record.diagnosis.evidence
    report = build_diagnosis_report(record)
    assert report.tool_calls == []
    markdown = render_report_markdown(report)
    assert "## 诊断对象" in markdown and "其他对象的历史检测（不用于当前结论）" in markdown
    assert "工具执行位置：NetPilot 服务主机" in markdown
    payload = json.loads(render_report_json(report))
    assert payload["diagnostic_target"]["subject"] == "user_client"
    assert payload["archived_tool_calls"][0]["execution_context"] == "netpilot_host"
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute("SELECT value FROM netpilot_metadata WHERE key='schema_version'").fetchone()[0] == "3"
    assert counts["dns_lookup"] == 1


@pytest.mark.parametrize("version", [1,2,3,4,5,6])
def test_dt13_legacy_defaults_do_not_infer_target_from_old_network_tools(tmp_path,version):
    app,_ = local_app(tmp_path)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        response = client.post("/api/chat",json={"session_id":sid,"message":"检查 NetPilot 服务器的 DNS，调用 dns_lookup"}).json()
        record = app.state.diagnosis_repository.get(owner,UUID(response["record_id"]))
    payload = record.model_dump(mode="json",exclude={"diagnostic_target"})
    payload["schema_version"] = version
    for tool in payload["tool_calls"]:
        for key in ("target_subject","target_version","execution_context","execution_scope"):
            tool.pop(key,None)
    for turn in payload["conversation_turns"]:
        turn.pop("target_subject",None)
        turn.pop("target_version",None)
    with sqlite3.connect(tmp_path / "target.db") as connection:
        connection.execute("UPDATE diagnosis_records SET schema_version=?, snapshot_json=?",(version,json.dumps(payload)))
    reopened = SQLiteDiagnosisRepository(tmp_path / "target.db").get(owner,record.record_id)
    assert reopened.diagnostic_target.subject == "unknown"
    assert reopened.diagnostic_target.execution_context == "unavailable"
    assert reopened.tool_calls[0].target_subject == "unknown"
    assert reopened.tool_calls[0].execution_context == "unavailable"
    assert "未记录" in render_report_markdown(build_diagnosis_report(reopened))


def test_target_patch_storage_failure_does_not_commit_session(tmp_path,monkeypatch):
    app,_ = local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        session = client.post("/api/session").json()
        def fail(*args,**kwargs):
            raise DiagnosisStorageError("private-error-detail")
        monkeypatch.setattr(app.state.diagnosis_repository,"update_diagnostic_target",fail)
        failed = client.patch("/api/session/diagnostic-target",json={"session_id":session["session_id"],"subject":"netpilot_host"})
        assert failed.status_code == 503 and "private-error" not in failed.text
        assert client.get(f"/api/session/{session['session_id']}").json() == session
