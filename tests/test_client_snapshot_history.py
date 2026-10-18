from datetime import datetime, timedelta, timezone
import json
import sqlite3
from uuid import UUID
from fastapi.testclient import TestClient
from conftest import register_test_user
from client_snapshot_helpers import payload, upload
from target_helpers import local_app
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.reports import build_diagnosis_report, render_report_json, render_report_markdown


def test_cs15_cs16_history_reopen_export_privacy_and_no_fake_tools_or_turns(tmp_path):
    app, counts = local_app(tmp_path)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        value = payload("dns_failure")
        value["client"]["hostname"] = "private-cs-hostname"
        value["adapters"][0]["interface_alias"] = "private-cs-interface"
        assert upload(client,sid,value).status_code == 200
        chat = client.post("/api/chat",json={"session_id":sid,"message":"根据快照分析我的电脑 DNS"})
        assert chat.status_code == 200,chat.text
        body = chat.json(); rid=UUID(body["record_id"])
        assert body["metrics"]["tool_calls"] == body["metrics"]["network_tool_calls"] == 0
        assert body["tool_calls"] == []
        assert len(body["client_evidence"]) == 5
        assert sum(item["title"] == "收到客户端诊断快照" for item in body["reasoning_trace"]) == 1
        first = client.get(f"/api/diagnoses/{rid}").json()
        assert first["turn_count"] == len(first["conversation_turns"]) == 1
        replacement = upload(client,sid,payload()).json()
        interim = client.get(f"/api/diagnoses/{rid}").json()
        assert interim["turn_count"] == 1 and len(interim["client_evidence"]) == 10
        report = client.get(f"/api/diagnoses/{rid}/report").json()
        assert "尚待分析" in report["conclusion"]
        stream=client.post("/api/chat/stream",json={"session_id":sid,"message":"生成诊断报告"})
        block=next(part for part in stream.text.split("\n\n") if "event: complete" in part)
        streamed=json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))["response"]
        assert streamed["tool_calls"] == [] and len(streamed["client_evidence"]) == 10
        assert "诊断报告" in streamed["answer"]
        for format in ["json","markdown"]:
            exported=client.get(f"/api/diagnoses/{rid}/export?format={format}")
            assert exported.status_code == 200
            assert "private-cs" not in exported.text
            assert "192.168.10.20" not in exported.text  # local interface addresses minimized
            assert "client_instance_id" not in exported.text and "ipv4_addresses" not in exported.text
        assert sum(counts.values()) == 0
    repository=SQLiteDiagnosisRepository(tmp_path / "target.db")
    record=repository.get(owner,rid)
    assert record.schema_version == 7 and record.turn_count == len(record.conversation_turns) == 2
    assert record.client_snapshot_summary.snapshot_sequence == 2
    assert len(record.client_evidence) == 10 and sum(item.superseded for item in record.client_evidence) == 5
    assert sum(item.title == "收到客户端诊断快照" for item in record.reasoning_trace) == 2
    assert not record.tool_calls
    assert "原始" not in render_report_json(build_diagnosis_report(record))
    markdown=render_report_markdown(build_diagnosis_report(record))
    assert "## 客户端诊断快照" in markdown and "历史归档" in markdown
    with sqlite3.connect(repository.path) as connection:
        raw=connection.execute("SELECT snapshot_json FROM diagnosis_records").fetchone()[0]
        assert "private-cs" not in raw and "client_instance_id" not in raw
        assert connection.execute("SELECT value FROM netpilot_metadata WHERE key='schema_version'").fetchone()[0] == "3"


def test_dedup_does_not_touch_persisted_record_trace_or_turns(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid=client.post("/api/session").json()["session_id"]
        initial=client.post("/api/chat",json={"session_id":sid,"message":"我的电脑网络打不开"}).json()
        value=payload()
        assert upload(client,sid,value).status_code == 200
        before=client.get(f'/api/diagnoses/{initial["record_id"]}').json()
        assert upload(client,sid,value).json()["duplicate"]
        after=client.get(f'/api/diagnoses/{initial["record_id"]}').json()
        assert after == before
        assert after["turn_count"] == 1
        client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"netpilot_host"})
        archived=client.get(f'/api/diagnoses/{initial["record_id"]}').json()
        assert not archived["client_snapshot_summary"]["applicable"]


def test_report_stale_is_recomputed_on_read(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner=register_test_user(client)
        sid=client.post("/api/session").json()["session_id"]
        upload(client,sid,payload())
        response=client.post("/api/chat",json={"session_id":sid,"message":"分析已有网络证据"}).json()
        rid=UUID(response["record_id"])
        with sqlite3.connect(tmp_path / "target.db") as connection:
            row=connection.execute("SELECT snapshot_json FROM diagnosis_records").fetchone()[0]
            data=json.loads(row)
            past=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
            data["client_snapshot_summary"]["expires_at"]=past
            for item in data["client_evidence"]: item["expires_at"]=past
            connection.execute("UPDATE diagnosis_records SET snapshot_json=?",(json.dumps(data),))
        reloaded=SQLiteDiagnosisRepository(tmp_path / "target.db").get(owner,rid)
        assert reloaded.client_snapshot_summary.stale
        assert all(item.stale for item in reloaded.client_evidence)
        assert "不代表现在" in build_diagnosis_report(reloaded).conclusion
        changed=client.post("/api/chat",json={"session_id":sid,"message":"重新检查我的电脑网络"})
        assert changed.status_code == 200
        cleared=client.get(f"/api/diagnoses/{rid}").json()
        assert not cleared["client_snapshot_summary"]["applicable"]
        assert not cleared["diagnosis"]["evidence"]


def test_snapshot_does_not_cross_owner_history_report(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as alice,TestClient(app) as bob:
        register_test_user(alice); register_test_user(bob)
        sid=alice.post("/api/session").json()["session_id"]
        upload(alice,sid,payload())
        rid=alice.post("/api/chat",json={"session_id":sid,"message":"分析网络证据"}).json()["record_id"]
        for suffix in ["", "/report", "/export?format=json"]:
            assert bob.get(f"/api/diagnoses/{rid}{suffix}").status_code == 404


def test_knowledge_turn_does_not_claim_new_snapshot_was_analyzed(tmp_path):
    app,_=local_app(tmp_path,rag=True)
    with TestClient(app) as client:
        register_test_user(client)
        sid=client.post("/api/session").json()["session_id"]
        upload(client,sid,payload("dns_failure"))
        analyzed=client.post("/api/chat",json={"session_id":sid,"message":"根据快照分析网络"}).json()
        rid=analyzed["record_id"]
        knowledge=client.post("/api/chat",json={"session_id":sid,"message":"天津大学 VPN 怎么使用？请检索知识库并标出来源。"})
        assert knowledge.status_code == 200
        report=client.get(f"/api/diagnoses/{rid}/report").json()
        assert "快照分析" in report["conclusion"]
        upload(client,sid,payload())
        client.post("/api/chat",json={"session_id":sid,"message":"天津大学 VPN 怎么使用？请检索知识库并标出来源。"})
        report=client.get(f"/api/diagnoses/{rid}/report").json()
        assert "尚待分析" in report["conclusion"]
