from uuid import UUID,uuid4
import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from client_snapshot_helpers import payload,upload
from target_helpers import local_app


def setup_plan(client):
    owner=register_test_user(client)
    sid=client.post("/api/session").json()["session_id"]
    assert upload(client,sid,payload("dns_failure")).status_code == 200
    result=client.post("/api/session/remediation-plan",json={"session_id":sid})
    assert result.status_code == 200,result.text
    return owner,sid,result.json()["remediation_plan"]


def test_gr10_gr11_feedback_statuses_idempotence_and_no_turns(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,plan=setup_plan(client)
        step=plan["steps"][0]
        body={"session_id":sid,"action":"complete","outcome":"no_change","user_note":"网页仍打不开"}
        url=f'/api/session/remediation-plan/steps/{step["step_id"]}'
        result=client.patch(url,json=body)
        assert result.status_code == 200,result.text
        plan=result.json()["remediation_plan"]
        assert plan["status"] == "in_progress" and plan["steps"][0]["status"] == "completed"
        assert plan["steps"][0]["outcome"] == "no_change"
        assert len(result.json()["reasoning_trace"]) == 1
        duplicate=client.patch(url,json=body)
        assert duplicate.json()["reasoning_trace"] == []
        assert duplicate.json()["remediation_plan"] == plan
        assert client.patch(url,json={**body,"action":"skip","outcome":"unknown"}).status_code == 409
        for item in plan["steps"][1:]:
            response=client.patch(f'/api/session/remediation-plan/steps/{item["step_id"]}',json={"session_id":sid,"action":"skip"})
            assert response.status_code == 200
        ended=response.json()["remediation_plan"]
        assert ended["status"] == "completed"
        assert all(item["outcome"] == "unknown" for item in ended["steps"][1:])
        assert app.state.sessions.task_state(UUID(sid),owner).turn_index == 0
        assert app.state.diagnosis_repository.count(owner) == 0
        assert sum(counts.values()) == 0


def test_gr16_ownership_auth_busy_and_no_overrides(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as anon:
        owner,sid,plan=setup_plan(alice)
        register_test_user(bob)
        url=f'/api/session/remediation-plan/steps/{plan["steps"][0]["step_id"]}'
        for client,status in [(bob,404),(anon,401)]:
            assert client.get("/api/session/remediation-plan",params={"session_id":sid}).status_code == status
            assert client.post("/api/session/remediation-plan",json={"session_id":sid}).status_code == status
            assert client.patch(url,json={"session_id":sid,"action":"skip"}).status_code == status
        for key in ["command","risk_override","admin_override","user_id"]:
            response=alice.post("/api/session/remediation-plan",json={"session_id":sid,key:"secret-not-echoed"})
            assert response.status_code == 422 and "secret-not-echoed" not in response.text
        app.state.sessions.begin_turn(UUID(sid),owner)
        assert alice.post("/api/session/remediation-plan",json={"session_id":sid}).status_code == 409
        app.state.sessions.abort_turn(UUID(sid))
        assert alice.patch(f"/api/session/remediation-plan/steps/{uuid4()}",json={"session_id":sid,"action":"skip"}).status_code == 404


def test_gr08_target_environment_and_snapshot_supersede(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        _,sid,first=setup_plan(client)
        def get():return client.get("/api/session/remediation-plan",params={"session_id":sid}).json()
        assert get()["remediation_plan"] == first
        client.patch("/api/session/environment/user",json={"session_id":sid,"network_access":"off_campus"})
        assert get()["remediation_plan"]["status"] == "superseded"
        second=client.post("/api/session/remediation-plan",json={"session_id":sid}).json()["remediation_plan"]
        assert second["plan_version"] == 2 and second["plan_id"] != first["plan_id"]
        upload(client,sid,payload())
        assert get()["remediation_plan"]["status"] == "superseded"
        third=client.post("/api/session/remediation-plan",json={"session_id":sid}).json()["remediation_plan"]
        assert third["plan_version"] == 3
        client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"netpilot_host"})
        assert get()["remediation_plan"]["status"] == "superseded"
        host=client.post("/api/session/remediation-plan",json={"session_id":sid}).json()["remediation_plan"]
        assert host["target_subject"] == "netpilot_host" and host["target_version"] == 2
        assert client.patch(f'/api/session/remediation-plan/steps/{first["steps"][0]["step_id"]}',json={"session_id":sid,"action":"skip"}).status_code in {404,409}


def test_plan_update_storage_failure_keeps_original_state(tmp_path,monkeypatch):
    from netpilot.history import DiagnosisStorageError
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,plan=setup_plan(client)
        def fail(*args):raise DiagnosisStorageError("private-error")
        monkeypatch.setattr(app.state.diagnosis_repository,"update_remediation",fail)
        response=client.patch(f'/api/session/remediation-plan/steps/{plan["steps"][0]["step_id"]}',json={"session_id":sid,"action":"complete","outcome":"no_change"})
        assert response.status_code == 503 and "private-error" not in response.text
        task=app.state.sessions.task_state(UUID(sid),owner)
        assert task.remediation_plan.steps[0].status == "pending"


def test_get_plan_route_does_not_shadow_session_uuid_route(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid=client.post("/api/session").json()["session_id"]
        response=client.get("/api/session/remediation-plan",params={"session_id":sid})
        assert response.status_code == 200,response.text
        assert response.json()["remediation_plan"] is None


def test_gr02_clarified_web_symptom_supports_limited_manual_plan(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid=client.post("/api/session").json()["session_id"]
        answer=client.post("/api/chat",json={"session_id":sid,"message":"网页打不开"})
        assert answer.status_code == 200 and answer.json()["remediation_plan"] is None
        result=client.post("/api/session/remediation-plan",json={"session_id":sid}).json()
        assert result["remediation_plan"]["readiness"] == "limited"
        assert all(not step["changes_system_state"] for step in result["remediation_plan"]["steps"])


def test_not_ready_empty_plan_can_be_replaced_after_text_clarification(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid=client.post("/api/session").json()["session_id"]
        first=client.post("/api/session/remediation-plan",json={"session_id":sid}).json()["remediation_plan"]
        assert first["readiness"] == "not_ready"
        client.post("/api/chat",json={"session_id":sid,"message":"网页打不开"})
        second=client.post("/api/session/remediation-plan",json={"session_id":sid}).json()["remediation_plan"]
        assert second["readiness"] == "limited" and second["plan_version"] == 2
