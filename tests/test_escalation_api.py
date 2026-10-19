from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from target_helpers import local_app
from test_remediation_api import setup_plan

BASE="/api/session/escalation-package"


def test_ep02_ep16_ep25_generate_read_download_and_idempotent_trace(tmp_path):
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=setup_plan(client)
        before=app.state.sessions.task_state(UUID(sid),owner).resolution.model_dump()
        first=client.post(BASE,json={"session_id":sid})
        assert first.status_code==200,first.text
        data=first.json();p=data["packages"][-1]
        assert data["reasoning_trace"][-1]["title"]=="报修材料信息不完整"
        second=client.post(BASE,json={"session_id":sid}).json()
        assert second["packages"]==data["packages"] and not second["reasoning_trace"]
        assert client.get(BASE,params={"session_id":sid}).json()["packages"]==data["packages"]
        assert client.get(f'{BASE}/{p["package_id"]}',params={"session_id":sid}).json()==p
        for format in ["md","json"]:
            result=client.get(f'{BASE}/{p["package_id"]}/export',params={"session_id":sid,"format":format})
            assert result.status_code==200 and result.headers["cache-control"]=="no-store"
            assert "attachment" in result.headers["content-disposition"]
        assert app.state.sessions.task_state(UUID(sid),owner).resolution.model_dump()==before
        assert app.state.sessions.task_state(UUID(sid),owner).turn_index==0 and sum(counts.values())==0
        assert first.headers["cache-control"]=="no-store"


def test_ep18_owner_and_anonymous_all_routes(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as anon:
        _,sid,_=setup_plan(alice);register_test_user(bob)
        pid=alice.post(BASE,json={"session_id":sid}).json()["packages"][-1]["package_id"]
        for client,code in [(bob,404),(anon,401)]:
            assert client.post(BASE,json={"session_id":sid}).status_code==code
            for url in [BASE,f"{BASE}/{pid}",f"{BASE}/{pid}/export"]:
                assert client.get(url,params={"session_id":sid}).status_code==code
        app.state.sessions.clear()  # same checks through the persisted fallback
        assert bob.get(f"{BASE}/{pid}/export",params={"session_id":sid}).status_code==404
        assert alice.get(f"{BASE}/{pid}/export",params={"session_id":sid}).status_code==200


@pytest.mark.parametrize("key",["evidence","resolution","reason_code","user_id","privacy_policy","command"])
def test_input_allowlist_does_not_echo_forbidden_payloads(tmp_path,key):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client);sid=client.post("/api/session").json()["session_id"]
        result=client.post(BASE,json={"session_id":sid,key:"private-secret-sentinel"})
        assert result.status_code==422 and "private-secret-sentinel" not in result.text


@pytest.mark.parametrize("failure",["builder","storage"])
def test_failures_rollback_packages_preserve_session_history_resolution(tmp_path,monkeypatch,failure):
    from netpilot.history import DiagnosisStorageError
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=setup_plan(client)
        before=app.state.sessions.task_state(UUID(sid),owner).model_dump_json()
        def fail(*a,**kw): raise DiagnosisStorageError("private-failure")
        if failure=="builder":monkeypatch.setattr(app.state.sessions,"_ensure_escalation",fail)
        else:monkeypatch.setattr(app.state.diagnosis_repository,"update_escalation",fail)
        result=client.post(BASE,json={"session_id":sid})
        assert result.status_code==503 and "private-failure" not in result.text
        assert app.state.sessions.task_state(UUID(sid),owner).model_dump_json()==before
        assert client.get(f"/api/session/{sid}").status_code==200


def test_busy_and_export_size_limit(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=setup_plan(client)
        app.state.sessions.begin_turn(UUID(sid),owner)
        assert client.post(BASE,json={"session_id":sid}).status_code==409
        app.state.sessions.abort_turn(UUID(sid))
        pid=client.post(BASE,json={"session_id":sid}).json()["packages"][-1]["package_id"]
        app.state.settings.diagnosis_report_max_bytes=1024
        assert client.get(f"{BASE}/{pid}/export",params={"session_id":sid}).status_code==413


def test_broken_current_builder_does_not_break_existing_artifact_exports(tmp_path,monkeypatch):
    import netpilot.escalation.builder as builder
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        _,sid,_=setup_plan(client)
        p=client.post(BASE,json={"session_id":sid}).json()["packages"][-1]
        def fail(*a,**kw):raise ValueError("secret-current-state")
        monkeypatch.setattr(builder,"_content",fail)
        assert client.post(BASE,json={"session_id":sid}).status_code==503
        result=client.get(BASE,params={"session_id":sid})
        assert result.status_code==200 and result.json()["freshness_unknown"]
        export=client.get(f'{BASE}/{p["package_id"]}/export',params={"session_id":sid,"format":"json"})
        assert export.status_code==200 and export.json()==p and "secret-current-state" not in export.text
