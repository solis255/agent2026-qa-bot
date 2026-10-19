import json
import sqlite3
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from client_snapshot_helpers import payload,upload
from target_helpers import local_app
from test_remediation_api import setup_plan
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.reports import build_diagnosis_report,render_report_markdown,render_report_json


def test_gr17_gr18_history_reopens_and_report_retains_feedback(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,plan=setup_plan(client)
        step=plan["steps"][0]
        feedback=client.patch(f'/api/session/remediation-plan/steps/{step["step_id"]}',json={"session_id":sid,"action":"complete","outcome":"no_change","user_note":"仍未改善 <script>bad()</script>"})
        assert feedback.status_code == 200
        chat=client.post("/api/chat",json={"session_id":sid,"message":"还是不行，怎么解决？"})
        assert chat.status_code == 200,chat.text
        body=chat.json();rid=UUID(body["record_id"])
        assert body["remediation_plan"]["plan_id"] == plan["plan_id"]
        assert body["metrics"]["network_tool_calls"] == body["metrics"]["tool_calls"] == 0
        restored=client.get(f"/api/session/{sid}").json()
        assert restored["remediation_plan"]["steps"][0]["outcome"] == "no_change"
        assert sum(item["title"] == "生成修复计划" for item in body["reasoning_trace"]) == 1
        # Feedback after the history row exists updates it without inventing a Turn.
        current=body["remediation_plan"]
        second=current["steps"][1]
        assert client.patch(f'/api/session/remediation-plan/steps/{second["step_id"]}',json={"session_id":sid,"action":"skip"}).status_code == 200
        record=client.get(f"/api/diagnoses/{rid}").json()
        assert record["turn_count"] == len(record["conversation_turns"]) == 1
        assert record["remediation_plan"]["steps"][1]["status"] == "skipped"
        assert sum(counts.values()) == 0
    repo=SQLiteDiagnosisRepository(tmp_path/"target.db")
    record=repo.get(owner,rid)
    assert record.schema_version == 10 and record.remediation_plan.steps[0].outcome == "no_change"
    report=build_diagnosis_report(record)
    markdown=render_report_markdown(report)
    assert "## 修复计划" in markdown and "no_change" in markdown and "回滚" in markdown and "验证" in markdown
    assert "<script>bad()" not in markdown
    assert json.loads(render_report_json(report))["remediation_plan"]["steps"][1]["status"] == "skipped"
    with sqlite3.connect(repo.path) as connection:
        assert connection.execute("SELECT value FROM netpilot_metadata WHERE key='schema_version'").fetchone()[0] == "3"


@pytest.mark.parametrize("version",range(1,8))
def test_legacy_history_never_infers_plan_from_answer(tmp_path,version):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner=register_test_user(client)
        sid=client.post("/api/session").json()["session_id"]
        response=client.post("/api/chat",json={"session_id":sid,"message":"我的电脑网络打不开"}).json()
        rid=UUID(response["record_id"])
    with sqlite3.connect(tmp_path/"target.db") as connection:
        data=json.loads(connection.execute("SELECT snapshot_json FROM diagnosis_records").fetchone()[0])
        for key in ["remediation_plan","remediation_plan_history","remediation_readiness"]:data.pop(key,None)
        data["schema_version"]=version
        data["answer"]="建议重新连接当前网络。"
        connection.execute("UPDATE diagnosis_records SET schema_version=?,snapshot_json=?",(version,json.dumps(data)))
    record=SQLiteDiagnosisRepository(tmp_path/"target.db").get(owner,rid)
    assert record.remediation_plan is None and not record.remediation_plan_history


def test_knowledge_and_report_turns_preserve_current_plan(tmp_path):
    app,_=local_app(tmp_path,rag=True)
    with TestClient(app) as client:
        _,sid,plan=setup_plan(client)
        for index,message in enumerate(["天津大学 VPN 怎么使用？请检索知识库并标出来源。","生成诊断报告","你刚才没有回答我的问题"]):
            response=client.post("/api/chat",json={"session_id":sid,"message":message})
            assert response.status_code == 200,response.text
            assert response.json()["remediation_plan"]["plan_id"] == plan["plan_id"]
            # The first actual Turn persists the earlier API-only event once.
            assert sum(item["title"] == "生成修复计划" for item in response.json()["reasoning_trace"]) == (1 if index == 0 else 0)


def test_sources_prefer_official_and_community_only_is_marked():
    from remediation_helpers import task_with_snapshot,build
    *_,task=task_with_snapshot(network_access="campus_wifi")
    community={"source_ref":"community_ref","title":"社区资料","source":"https://example.com/community","source_type":"community"}
    official={"source_ref":"official_ref","title":"官方资料","source":"https://example.com/official","source_type":"official"}
    plan=build(task,knowledge_sources=[community,official])
    step=next(item for item in plan.steps if item.template_id == "check_official_guide")
    assert step.source_refs == ["official_ref"]
    plan=build(task,knowledge_sources=[community])
    step=next(item for item in plan.steps if item.template_id == "check_official_guide")
    assert "需官方核验" in step.rationale
