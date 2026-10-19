from uuid import UUID
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from target_helpers import local_app
from test_remediation_api import setup_plan
from verification_helpers import complete_step,waiting_cycle
from client_snapshot_helpers import upload,payload
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.reports import build_diagnosis_report,render_report_markdown,render_report_json


def test_bv17_bv18_bv19_reload_report_and_trace(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,plan=setup_plan(client)
        chat=client.post("/api/chat",json={"session_id":sid,"message":"生成诊断报告"}).json();rid=UUID(chat["record_id"])
        first=complete_step(client,sid,plan)
        assert upload(client,sid,payload()).status_code == 200
        record=client.get(f"/api/diagnoses/{rid}").json()
        assert record["turn_count"] == len(record["conversation_turns"]) == 1
    restored=SQLiteDiagnosisRepository(tmp_path/"target.db").get(owner,rid)
    cycle=restored.verification_cycles[-1]
    assert cycle.baseline.evidence_ids == tuple(first["baseline"]["evidence_ids"])
    assert cycle.result == "improved" and cycle.after and cycle.diffs
    assert set(cycle.baseline.evidence_ids).issubset({r.evidence_id for r in restored.client_evidence})
    titles={e.title for e in restored.reasoning_trace if e.event_origin == "verification"}
    assert {"记录修复前基线","开始修复后验证","完成修复前后对比"}.issubset(titles)
    report=build_diagnosis_report(restored);md=render_report_markdown(report)
    assert "## 修复前后验证" in md and "| 指标 / 目标 | 修复前 | 修复后 | 变化 |" in md
    assert "有改善" in md and "不代表故障已解决" in md
    assert json.loads(render_report_json(report))["verification_cycles"][-1]["result"] == "improved"
    assert sum(counts.values()) == 0


@pytest.mark.parametrize("version",range(1,9))
def test_legacy_has_no_invented_verification(tmp_path,version):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=setup_plan(client)
        rid=UUID(client.post("/api/chat",json={"session_id":sid,"message":"生成诊断报告"}).json()["record_id"])
    with sqlite3.connect(tmp_path/"target.db") as conn:
        data=json.loads(conn.execute("SELECT snapshot_json FROM diagnosis_records").fetchone()[0])
        data.pop("verification_cycles",None);data.pop("verification_evidence",None);data["schema_version"]=version
        conn.execute("UPDATE diagnosis_records SET schema_version=?,snapshot_json=?",(version,json.dumps(data)))
    assert SQLiteDiagnosisRepository(tmp_path/"target.db").get(owner,rid).verification_cycles == []


def test_context_and_followup_reuse_without_tools():
    from client_snapshot_helpers import import_snapshot
    from netpilot.verification.service import context
    from target_helpers import run
    agent,store,sid,owner,counts,llm,_=waiting_cycle()
    task,_,_=import_snapshot(store,sid,owner,payload())
    text=context(task.verification_cycles,task.diagnostic_target,task.task_version)
    assert "VERIFICATION STATUS" in text and "Result: improved" in text
    result=run(agent,store,sid,owner,"现在怎么样？")
    assert "improved 不等于" in result.answer and result.steps == [] and not llm.calls
    assert sum(counts.values()) == 0
