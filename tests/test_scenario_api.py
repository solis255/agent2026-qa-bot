from __future__ import annotations

from fastapi.testclient import TestClient

from netpilot.config import Settings
from netpilot.main import create_app


def app_for(mode: str = "mock", *, enabled: bool = True):
    return create_app(
        Settings(
            _env_file=None,
            tju_api_key="scenario-test-key",
            tool_mode=mode,
            rag_enabled=False,
            scenario_switch_enabled=enabled,
        )
    )


def test_mock_scenarios_are_listed_with_current_state() -> None:
    with TestClient(app_for()) as client:
        response = client.get("/api/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert body["current"] == "healthy"
    assert body["switch_enabled"] is True
    assert {scenario["name"] for scenario in body["scenarios"]} == {
        "healthy",
        "dns_failure",
        "gateway_unreachable",
        "tcp_ssh_blocked",
        "http_failure",
        "partial_connectivity",
    }


def test_switching_scenario_clears_old_sessions_and_returns_a_new_one() -> None:
    application = app_for()
    with TestClient(application) as client:
        old_session = client.post("/api/session").json()["session_id"]
        response = client.post("/api/scenarios/dns_failure")
        stale = client.post(
            "/api/chat",
            json={"session_id": old_session, "message": "测试"},
        )

    assert response.status_code == 200
    assert response.json()["current"] == "dns_failure"
    assert response.json()["session_id"] != old_session
    assert response.json()["sessions_cleared"] == 1
    assert application.state.network_tools.provider.scenario.value == "dns_failure"
    assert stale.status_code == 404


def test_scenario_switch_is_disabled_by_default_and_invalid_names_are_rejected() -> None:
    with TestClient(app_for(enabled=False)) as client:
        disabled = client.post("/api/scenarios/dns_failure")
        invalid = client.post("/api/scenarios/arbitrary-command")

    assert disabled.status_code == 403
    assert invalid.status_code == 422


def test_local_mode_rejects_mock_scenario_endpoints() -> None:
    with TestClient(app_for("local")) as client:
        listed = client.get("/api/scenarios")
        switched = client.post("/api/scenarios/dns_failure")

    assert listed.status_code == 409
    assert switched.status_code == 409
