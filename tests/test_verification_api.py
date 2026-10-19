from uuid import UUID,uuid4
import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from target_helpers import local_app
from test_remediation_api import setup_plan
from verification_helpers import complete_step
from client_snapshot_helpers import payload,upload


def test_bv16_all_endpoints_owner_and_auth(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as anon:
        _,sid,plan=setup_plan(alice);cycle=complete_step(alice,sid,plan);vid=cycle["verification_id"]
        register_test_user(bob)
        for client,status in [(bob,404),(anon,401)]:
            assert client.get("/api/session/verification",params={"session_id":sid}).status_code == status
            for suffix,body in [("",{}),(f"/{vid}/start",{}),(f"/{vid}/user-observation",{"symptom_status":"unknown"})]:
                assert client.post("/api/session/verification"+suffix,json={"session_id":sid,**body}).status_code == status
        bad=alice.post("/api/session/verification",json={"session_id":sid,"command":"private-secret"})
        assert bad.status_code == 422 and "private-secret" not in bad.text
        assert alice.get("/api/session/verification",params={"session_id":sid}).headers["cache-control"] == "no-store"


def test_api_subjective_conflict_reverify_and_no_fake_turn(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,plan=setup_plan(client);cycle=complete_step(client,sid,plan);vid=cycle["verification_id"]
        url=f"/api/session/verification/{vid}/user-observation"
        feedback=client.post(url,json={"session_id":sid,"symptom_status":"improved_by_user_report","note":"好多了"})
        assert feedback.json()["verification_cycles"][-1]["result"] == "inconclusive"
        response=upload(client,sid,payload());assert response.status_code == 200,response.text
        assert response.json()["verification_cycles"][-1]["result"] == "improved"
        feedback=client.post(url,json={"session_id":sid,"symptom_status":"unchanged_by_user_report","note":"网页还是打不开"})
        assert feedback.json()["verification_cycles"][-1]["result"] == "inconclusive"
        duplicate=client.post(f"/api/session/verification/{vid}/start",json={"session_id":sid})
        assert len(duplicate.json()["verification_cycles"]) == 1
        new=client.post("/api/session/verification",json={"session_id":sid,"reverify":True})
        assert new.status_code == 200,new.text
        second=new.json()["verification_cycles"][-1]
        assert second["verification_sequence"] == 2 and second["baseline"]["task_version"] == 2
        restored=client.get(f"/api/session/{sid}").json()
        assert restored["verification_cycles"][-1]["status"] == "baseline_ready"
        assert app.state.sessions.task_state(UUID(sid),owner).turn_index == 0 and sum(counts.values()) == 0


def test_busy_and_storage_failure_atomic(tmp_path,monkeypatch):
    from netpilot.history import DiagnosisStorageError
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,plan=setup_plan(client)
        app.state.sessions.begin_turn(UUID(sid),owner)
        assert client.post("/api/session/verification",json={"session_id":sid}).status_code == 409
        app.state.sessions.abort_turn(UUID(sid))
        def fail(*a):raise DiagnosisStorageError("private")
        monkeypatch.setattr(app.state.diagnosis_repository,"update_remediation",fail)
        response=client.patch(f'/api/session/remediation-plan/steps/{plan["steps"][0]["step_id"]}',json={"session_id":sid,"action":"complete"})
        assert response.status_code == 503 and "private" not in response.text
        task=app.state.sessions.task_state(UUID(sid),owner)
        assert task.task_version == 1 and task.verification_cycles[-1].status == "baseline_ready"


def test_cannot_start_host_without_completed_step(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        _,sid,_=setup_plan(client)
        cycle=client.get("/api/session/verification",params={"session_id":sid}).json()["verification_cycles"][-1]
        assert client.post(f'/api/session/verification/{cycle["verification_id"]}/start',json={"session_id":sid}).status_code == 409


def test_host_api_timeline_history_and_repeat_dedup(tmp_path):
    from dataclasses import replace
    from netpilot.tools.schemas import ToolResult,DNSLookupData
    app,counts=local_app(tmp_path)
    registry=app.state.tool_registry
    original=registry._specs["dns_lookup"]
    registry._specs["dns_lookup"]=replace(original,handler=lambda **kw:ToolResult(success=True,tool="dns_lookup",summary="synthetic fail",data=DNSLookupData(resolved=False),duration_ms=1))
    with TestClient(app) as client:
        owner=register_test_user(client);sid=client.post("/api/session").json()["session_id"]
        assert client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"netpilot_host"}).status_code == 200
        chat=client.post("/api/chat",json={"session_id":sid,"message":"请诊断服务主机 github.com 的 DNS 解析"})
        assert chat.status_code == 200,chat.text
        body=chat.json();plan=body["remediation_plan"];assert plan and plan["steps"]
        cycle=complete_step(client,sid,plan)
        registry._specs["dns_lookup"]=original
        response=client.post(f'/api/session/verification/{cycle["verification_id"]}/start',json={"session_id":sid})
        assert response.status_code == 200,response.text
        result=response.json();assert result["verification_cycles"][-1]["result"] == "improved"
        calls=result["verification_tool_calls"]
        assert len(calls) == 1 and calls[0]["purpose"] == "verification" and calls[0]["arguments"] == {"domain":"github.com"}
        again=client.post(f'/api/session/verification/{cycle["verification_id"]}/start',json={"session_id":sid})
        assert again.json()["verification_tool_calls"] == calls
        assert counts["dns_lookup"] == sum(counts.values()) == 1
        record=client.get(f'/api/diagnoses/{body["record_id"]}').json()
        assert record["turn_count"] == 1 and len([c for c in record["tool_calls"] if c["purpose"] == "verification"]) == 1
        assert {e["evidence_id"] for e in record["verification_evidence"]}.issuperset(cycle["baseline"]["evidence_ids"])
        # A normal non-refresh analysis must not execute a tool.
        analysis=client.post("/api/chat",json={"session_id":sid,"message":"基于已有证据分析，不要重新检测"})
        assert analysis.status_code == 200 and sum(counts.values()) == 1


def test_step_outcome_is_subjective_and_conflict_not_silently_overridden(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        _,sid,plan=setup_plan(client)
        result=client.patch(f'/api/session/remediation-plan/steps/{plan["steps"][0]["step_id"]}',json={"session_id":sid,"action":"complete","outcome":"improved"})
        cycle=result.json()["verification_cycles"][-1]
        assert cycle["result"] == "inconclusive" and cycle["after"] is None
        assert cycle["user_observation"]["symptom_status"] == "improved_by_user_report"
        result=upload(client,sid,payload("dns_failure"))
        assert result.json()["verification_cycles"][-1]["result"] == "inconclusive"
