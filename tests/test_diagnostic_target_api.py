from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from target_helpers import local_app
from reasoning_helpers import trace_app


def test_dt01_dt10_target_api_session_refresh_ownership_and_no_environment_change(tmp_path):
    app,counts = local_app(tmp_path)
    with TestClient(app) as alice, TestClient(app) as bob:
        owner = register_test_user(alice)
        session = alice.post("/api/session").json()
        sid = session["session_id"]
        assert session["diagnostic_target"]["subject"] == "user_client"
        assert session["diagnostic_target"]["limitation_code"] == "remote_client_not_directly_observable"
        changed = alice.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"netpilot_host"})
        assert changed.status_code == 200
        assert changed.json()["target_version"] == 2
        assert changed.json()["limitation_code"] == "none"
        again = alice.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"netpilot_host"})
        assert again.json() == changed.json()
        restored = alice.get(f"/api/session/{sid}").json()
        assert restored["environment_profile"] == session["environment_profile"]
        assert restored["diagnostic_target"] == changed.json()
        register_test_user(bob)
        assert bob.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"user_client"}).status_code == 404
        assert bob.get(f"/api/session/{sid}").status_code == 404
        app.state.sessions.begin_turn(UUID(sid),owner)
        assert alice.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"user_client"}).status_code == 409
        app.state.sessions.abort_turn(UUID(sid))
        assert sum(counts.values()) == 0


@pytest.mark.parametrize("extra", [{"execution_context":"netpilot_host"},{"limitation_code":"none"},{"relationship_to_netpilot":"same_host"},{"target_version":100},{"source":"system"},{"local_tools_applicable":True}])
def test_client_cannot_forge_capabilities_or_target_metadata(tmp_path, extra):
    app,_ = local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        response = client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"user_client",**extra})
        assert response.status_code == 422
        assert all("input" not in error for error in response.json()["detail"])
        assert client.get(f"/api/session/{sid}").json()["diagnostic_target"]["target_version"] == 1


def test_unauthenticated_and_mock_target_readonly(tmp_path):
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        assert client.patch("/api/session/diagnostic-target",json={"session_id":str(UUID(int=1)),"subject":"netpilot_host"}).status_code == 401
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        assert client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"netpilot_host"}).status_code == 409
        assert client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"mock_client"}).status_code == 422
        assert client.get(f"/api/session/{sid}").json()["diagnostic_target"]["subject"] == "mock_client"
