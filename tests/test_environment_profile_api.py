from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from conftest import register_test_user
from netpilot.config import Settings
from netpilot.main import create_app
from reasoning_helpers import CASE_A, trace_app


@pytest.mark.parametrize("mode,expected", [("mock","mock"), ("local","remote_browser")])
def test_ep01_session_initializes_safe_client_mode(tmp_path, mode, expected):
    app = create_app(Settings(_env_file=None, tool_mode=mode, rag_enabled=False, diagnosis_history_enabled=False, diagnosis_db_path=tmp_path / "auth.db"))
    with TestClient(app) as client:
        register_test_user(client)
        response = client.post("/api/session")
        assert response.status_code == 201
        profile = response.json()["environment_profile"]
        assert profile["client_mode"] == expected
        assert profile["vpn_enabled"] is profile["proxy_enabled"] is None
        assert profile["os_family"] == "unknown"


def test_ep02_browser_patch_and_user_override_refresh_and_ownership(tmp_path):
    app = trace_app(tmp_path)
    with TestClient(app) as alice, TestClient(app) as bob:
        register_test_user(alice)
        sid = alice.post("/api/session").json()["session_id"]
        browser = {"session_id":sid, "browser_online":True, "browser_language":"zh-CN", "os_family":"windows", "effective_type":"4g"}
        result = alice.patch("/api/session/environment/browser", json=browser)
        assert result.status_code == 200
        assert result.json()["field_sources"]["os_family"] == {"source":"browser", "confidence":"medium"}
        assert result.json()["network_access"] == "unknown"
        result = alice.patch("/api/session/environment/user", json={"session_id":sid,"os_family":"macos", "network_access":"campus_wifi", "vpn_enabled":False})
        assert result.status_code == 200
        repeated = alice.patch("/api/session/environment/browser", json=browser).json()
        assert repeated["os_family"] == "macos"
        assert repeated["proxy_enabled"] is None
        assert alice.get(f"/api/session/{sid}").json()["environment_profile"] == repeated
        register_test_user(bob)
        for suffix in ("browser", "user"):
            assert bob.patch(f"/api/session/environment/{suffix}", json={"session_id":sid, "os_family":"linux"}).status_code == 404
        assert bob.get(f"/api/session/{sid}").status_code == 404
        assert alice.get(f"/api/session/{sid}").json()["environment_profile"] == repeated


@pytest.mark.parametrize("suffix,values", [
    ("browser", {"vpn_enabled":False}), ("browser", {"user_agent":"private-user-agent"}),
    ("browser", {"ssid":"private-wifi"}), ("browser", {"mac":"AA:BB:CC:DD:EE:FF"}),
    ("browser", {"geolocation":{"latitude":1}}), ("user", {"source":"server"}),
    ("user", {"field_sources":{"os_family":{"source":"server","confidence":"high"}}}),
    ("user", {"cookie":"secret-cookie-value"}), ("user", {"affected_service":"8.8.8.8"}),
])
def test_ep06_allowlist_privacy_and_no_echo(tmp_path, suffix, values):
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        response = client.patch(f"/api/session/environment/{suffix}", json={"session_id":sid, **values})
        assert response.status_code == 422
        assert all("input" not in error and "ctx" not in error for error in response.json()["detail"])
        assert client.get(f"/api/session/{sid}").json()["environment_profile"]["os_family"] == "unknown"
        assert client.get("/api/diagnoses").json()["items"] == []


def test_auth_busy_and_patch_does_not_add_history_turn(tmp_path):
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        assert client.patch("/api/session/environment/user", json={"session_id":str(UUID(int=1))}).status_code == 401
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        app.state.sessions.begin_turn(UUID(sid), owner)
        assert client.patch("/api/session/environment/user", json={"session_id":sid,"vpn_enabled":False}).status_code == 409
        app.state.sessions.abort_turn(UUID(sid))
        assert client.patch("/api/session/environment/user", json={"session_id":sid,"vpn_enabled":False}).status_code == 200
        assert client.get("/api/diagnoses").json()["items"] == []
        result = client.post("/api/chat", json={"session_id":sid,"message":CASE_A}).json()
        assert result["environment_profile"]["vpn_enabled"] is False
        assert result["environment_profile"]["client_mode"] == "mock"


def test_scenario_reset_has_new_profile_not_previous_users_environment(tmp_path):
    app = trace_app(tmp_path, scenario_switch_enabled=True)
    with TestClient(app) as client:
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        client.patch("/api/session/environment/user", json={"session_id":sid, "vpn_enabled":True})
        result = client.post("/api/scenarios/healthy")
        assert result.status_code == 200
        assert result.json()["session_id"] != sid
        assert result.json()["environment_profile"]["vpn_enabled"] is None
        assert result.json()["environment_profile"]["client_mode"] == "mock"
        assert client.get(f"/api/session/{sid}").status_code == 404
