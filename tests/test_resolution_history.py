from uuid import UUID
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from target_helpers import local_app
from test_resolution_api import recovered
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.reports import build_diagnosis_report,render_report_markdown,render_report_json


def test_rs20_rs21_history_report_list_and_target_atomic_update(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=recovered(client)
        chat=client.post("/api/chat",json={"session_id":sid,"message":"生成诊断报告"})
        assert chat.status_code == 200,chat.text
        rid=chat.json()["record_id"]
        confirm=client.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved"}).json()
        record=client.get(f"/api/diagnoses/{rid}").json()
        assert record["resolution"] == confirm["resolution"] and record["resolution_transitions"] == confirm["resolution_transitions"]
        assert record["turn_count"] == len(record["conversation_turns"]) == 1
        assert client.get("/api/diagnoses").json()["items"][0]["resolution"]["state"] == "resolved"
        restored=SQLiteDiagnosisRepository(tmp_path/"target.db").get(owner,UUID(rid))
        report=build_diagnosis_report(restored);markdown=render_report_markdown(report)
        assert "## 最终处理状态" in markdown and "已解决" in markdown and "用户确认" in markdown and "未提交外部工单" in markdown
        assert json.loads(render_report_json(report))["resolution"]["state"] == "resolved"
        assert client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"netpilot_host"}).status_code == 200
        record=client.get(f"/api/diagnoses/{rid}").json()
        live=client.get(f"/api/session/{sid}").json()
        assert record["resolution"]["state"] == "diagnosing" and record["resolution"]["reason_code"] == "target_changed"
        assert record["resolution_transitions"] == live["resolution_transitions"]
        assert record["metrics"]["reasoning_trace_steps"] == len(record["reasoning_trace"])
        assert any(t["to_state"] == "resolved" for t in record["resolution_transitions"]) and sum(counts.values()) == 0


@pytest.mark.parametrize("version",range(1,10))
def test_legacy_does_not_infer_resolution_from_answer(tmp_path,version):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=recovered(client)
        rid=UUID(client.post("/api/chat",json={"session_id":sid,"message":"生成诊断报告"}).json()["record_id"])
    with sqlite3.connect(tmp_path/"target.db") as connection:
        data=json.loads(connection.execute("SELECT snapshot_json FROM diagnosis_records").fetchone()[0])
        data.pop("resolution",None);data.pop("resolution_transitions",None);data["schema_version"]=version;data["answer"]="问题已解决，工单已提交。"
        connection.execute("UPDATE diagnosis_records SET schema_version=?,snapshot_json=?",(version,json.dumps(data)))
    restored=SQLiteDiagnosisRepository(tmp_path/"target.db").get(owner,rid)
    assert restored.resolution.state == "diagnosing" and restored.resolution_transitions == []


def test_rs16_recurrence_persisted_in_chat_and_sse(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        _,sid,_=recovered(client)
        rid=client.post("/api/chat",json={"session_id":sid,"message":"网页现在可以正常打开了"}).json()["record_id"]
        assert client.get(f"/api/diagnoses/{rid}").json()["resolution"]["state"] == "resolved"
        stream=client.post("/api/chat/stream",json={"session_id":sid,"message":"刚才好了，现在又打不开了"})
        block=next(b for b in stream.text.split("\n\n") if "event: complete" in b)
        response=json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))["response"]
        assert response["resolution"]["state"] == "diagnosing" and response["resolution"]["reason_code"] == "symptom_recurred"
        record=client.get(f"/api/diagnoses/{rid}").json()
        assert record["resolution"] == response["resolution"] and record["turn_count"] == 2
        assert any(t["to_state"] == "resolved" for t in record["resolution_transitions"]) and sum(counts.values()) == 0
