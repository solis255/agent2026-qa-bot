from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from target_helpers import local_app
from test_remediation_api import setup_plan
from verification_helpers import complete_step
from client_snapshot_helpers import payload,upload


def recovered(client):
    owner,sid,plan=setup_plan(client)
    complete_step(client,sid,plan)
    assert upload(client,sid,payload()).status_code == 200
    return owner,sid,plan


def test_rs04_rs17_confirm_idempotent_no_extra_turns_or_tools(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=recovered(client)
        result=client.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved"})
        assert result.status_code == 200,result.text
        body=result.json();assert body["resolution"]["state"] == "resolved"
        duplicate=client.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved"})
        assert duplicate.json()["resolution"] == body["resolution"]
        assert duplicate.json()["resolution_transitions"] == body["resolution_transitions"] and not duplicate.json()["reasoning_trace"]
        assert duplicate.headers["cache-control"] == "no-store"
        assert client.get(f"/api/session/{sid}").json()["resolution"] == body["resolution"]
        assert app.state.sessions.task_state(UUID(sid),owner).turn_index == 0 and sum(counts.values()) == 0


def test_rs19_auth_ownership_and_forbidden_state_patch(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as anon:
        _,sid,_=recovered(alice);register_test_user(bob)
        for client,status in [(bob,404),(anon,401)]:
            assert client.get("/api/session/resolution",params={"session_id":sid}).status_code == status
            assert client.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved"}).status_code == status
            assert client.post("/api/session/resolution/request-support",json={"session_id":sid}).status_code == status
        for key in ["state","user_id","objective_result","reason_code","command"]:
            bad=alice.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved",key:"private-secret"})
            assert bad.status_code == 422 and "private-secret" not in bad.text


def test_rs10_rs24_support_is_recommendation_and_idempotent(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client);sid=client.post("/api/session").json()["session_id"]
        result=client.post("/api/session/resolution/request-support",json={"session_id":sid})
        body=result.json();assert result.status_code == 200 and body["resolution"]["state"] == "escalated"
        assert body["resolution"]["reason_code"] == "user_requested"
        again=client.post("/api/session/resolution/request-support",json={"session_id":sid}).json()
        assert again["resolution"] == body["resolution"] and again["resolution_transitions"] == body["resolution_transitions"]
        assert sum(counts.values()) == 0 and "未向任何外部系统提交" in body["resolution"]["reason_summary"]


def test_busy_and_storage_error_preserve_case_state(tmp_path,monkeypatch):
    from netpilot.history import DiagnosisStorageError
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=recovered(client)
        before=app.state.sessions.task_state(UUID(sid),owner).resolution.model_dump()
        app.state.sessions.begin_turn(UUID(sid),owner)
        assert client.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved"}).status_code == 409
        app.state.sessions.abort_turn(UUID(sid))
        def fail(*a,**k):raise DiagnosisStorageError("private-failure")
        monkeypatch.setattr(app.state.diagnosis_repository,"update_resolution",fail)
        result=client.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved"})
        assert result.status_code == 503 and "private-failure" not in result.text
        assert app.state.sessions.task_state(UUID(sid),owner).resolution.model_dump() == before


def test_explicit_confirmation_updates_12e_observation_without_changing_objective_checks(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        _,sid,_=recovered(client)
        original=client.get("/api/session/verification",params={"session_id":sid}).json()["verification_cycles"][-1]
        negative=client.post(f'/api/session/verification/{original["verification_id"]}/user-observation',json={"session_id":sid,"symptom_status":"unchanged_by_user_report"}).json()
        assert negative["verification_cycles"][-1]["result"] == "inconclusive"
        assert negative["resolution"]["state"] == "improved" and negative["resolution"]["user_confirmation"] == "not_resolved"
        result=client.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved"}).json()
        assert result["resolution"]["state"] == "resolved"
        latest=client.get("/api/session/verification",params={"session_id":sid}).json()["verification_cycles"][-1]
        assert latest["checks"] == original["checks"] and latest["result"] == "improved"


def test_user_says_fixed_without_after_does_not_resolve(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client);sid=client.post("/api/session").json()["session_id"]
        response=client.post("/api/chat",json={"session_id":sid,"message":"好了"})
        assert response.status_code == 200,response.text
        assert response.json()["resolution"]["state"] == "improved"
        assert response.json()["resolution"]["user_confirmation"] == "resolved" and sum(counts.values()) == 0


def test_genuine_worsening_with_positive_confirmation_cannot_resolve(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client);sid=client.post("/api/session").json()["session_id"]
        before=payload();before["checks"][0].update(status="abnormal",result={"addresses":[],"error_code":"dns_query_failed"})
        assert upload(client,sid,before).status_code == 200
        plan=client.post("/api/session/remediation-plan",json={"session_id":sid}).json()["remediation_plan"]
        complete_step(client,sid,plan)
        after=payload();after["checks"][1].update(status="abnormal",result={"addresses":[],"error_code":"dns_query_failed"})
        result=upload(client,sid,after).json()
        assert result["resolution"]["objective_result"] == "worsened"
        result=client.post("/api/session/resolution/confirm",json={"session_id":sid,"status":"resolved"}).json()
        assert result["resolution"]["state"] != "resolved" and result["resolution"]["objective_result"] == "worsened"


def test_mock_can_complete_case_with_only_mock_handlers():
    from dataclasses import replace
    from uuid import uuid4
    from netpilot.agent import SessionStore,AgentOrchestrator
    from netpilot.tools.schemas import ToolResult,DNSLookupData
    from target_helpers import registry_and_counts,TargetLLM,run
    service,registry,counts=registry_and_counts("mock")
    original=registry._specs["dns_lookup"]
    registry._specs["dns_lookup"]=replace(original,handler=lambda **kw:ToolResult(success=True,tool="dns_lookup",summary="模拟 DNS 异常",data=DNSLookupData(resolved=False),duration_ms=1))
    store=SessionStore(provider_kind="mock",environment_client_mode="mock");owner=uuid4();sid=store.create(owner).session_id
    agent=AgentOrchestrator(TargetLLM(),registry)
    result=run(agent,store,sid,owner,"请诊断 github.com 的 DNS 故障")
    plan=result.remediation_plan
    from netpilot.remediation.models import StepFeedback
    task,_=store.remediation(sid,owner,step_id=plan.steps[0].step_id,feedback=StepFeedback(session_id=sid,action="complete"))
    registry._specs["dns_lookup"]=original
    task,_=store.verification(sid,owner,action="start",cycle_id=task.verification_cycles[-1].verification_id,registry=registry)
    task,_=store.resolution_action(sid,owner,action="confirm",confirmation="resolved")
    assert task.resolution.state == "resolved" and task.diagnostic_target.subject == "mock_client"
    assert all(r.execution_scope == "mock_target" for r in task.evidence)
    assert counts["dns_lookup"] == 1
