from __future__ import annotations

import socket
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from netpilot.agent.evidence import finding_status
from netpilot.config import Settings
from netpilot.main import create_app
from netpilot.tools.custom_scenarios import (
    CustomMockScenario,
    CustomScenarioBehavior,
    CustomScenarioExistsError,
    CustomScenarioLimitError,
)
from netpilot.tools.mock_network import MockNetworkProvider


def custom_payload(name: str = "dns_lab") -> dict[str, object]:
    return {
        "name": name,
        "label": "自定义 DNS 与 HTTP 故障",
        "description": "公网 Ping 正常，但 DNS、TCP、HTTP 和路由追踪按需失败。",
        "behavior": {
            "network_configured": True,
            "ping_reachable": True,
            "ping_packet_loss_percent": 25,
            "dns_resolved": False,
            "tcp_connected": False,
            "http_reachable": False,
            "http_status_code": None,
            "traceroute_reached": False,
        },
    }


def custom_app(
    mode: str = "mock",
    *,
    enabled: bool = True,
    limit: int = 20,
):
    return create_app(
        Settings(
            _env_file=None,
            tju_api_key="custom-scenario-test-key",
            tool_mode=mode,
            rag_enabled=False,
            scenario_switch_enabled=enabled,
            custom_scenario_max_count=limit,
        )
    )


def test_custom_behavior_rejects_inconsistent_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CustomScenarioBehavior(
            ping_reachable=False,
            ping_packet_loss_percent=10,
        )
    with pytest.raises(ValidationError):
        CustomScenarioBehavior(
            http_reachable=False,
            http_status_code=200,
        )
    with pytest.raises(ValidationError):
        CustomMockScenario.model_validate(
            {**custom_payload(), "command": "ping example.com"}
        )


def test_custom_provider_controls_all_six_tools_without_external_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("custom Mock scenario attempted external I/O")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    scenario = CustomMockScenario.model_validate(custom_payload())
    provider = MockNetworkProvider(max_custom_scenarios=2)
    provider.add_custom_scenario(scenario)
    provider.set_scenario(scenario.name)

    network = provider.get_network_info()
    ping = provider.ping_host("1.1.1.1", count=4)
    dns = provider.dns_lookup("example.com")
    tcp = provider.tcp_check("example.com", 443)
    http = provider.http_check("https://example.com")
    trace = provider.traceroute("example.com")

    assert all(item.success for item in (network, ping, dns, tcp, http, trace))
    assert network.data.default_gateway is not None
    assert ping.data.reachable is True and ping.data.packet_loss == 25
    assert dns.data.resolved is False
    assert tcp.data.connected is False
    assert http.data.reachable is False and http.data.request_sent is True
    assert trace.data.reached_destination is False


def test_custom_provider_preserves_built_ins_and_enforces_registry_limit() -> None:
    provider = MockNetworkProvider(max_custom_scenarios=1)
    first = CustomMockScenario.model_validate(custom_payload("first_lab"))
    second = CustomMockScenario.model_validate(custom_payload("second_lab"))

    with pytest.raises(CustomScenarioExistsError):
        provider.add_custom_scenario(
            CustomMockScenario.model_validate(custom_payload("healthy"))
        )
    provider.add_custom_scenario(first)
    with pytest.raises(CustomScenarioLimitError):
        provider.add_custom_scenario(second)

    provider.set_scenario(first.name)
    assert provider.delete_custom_scenario(first.name) is True
    assert provider.scenario_name == "healthy"


def test_custom_http_error_status_is_classified_as_abnormal_evidence() -> None:
    behavior = CustomScenarioBehavior(http_reachable=True, http_status_code=503)
    scenario = CustomMockScenario(
        name="http_503_lab",
        label="HTTP 503",
        description="连接成功但应用返回临时不可用。",
        behavior=behavior,
    )
    provider = MockNetworkProvider()
    provider.add_custom_scenario(scenario)
    provider.set_scenario(scenario.name)
    result = provider.http_check("https://example.com")

    assert result.success is True
    assert result.data.reachable is True
    assert result.data.status_code == 503
    assert finding_status(
        "http_check",
        result.success,
        result.data.model_dump(mode="json"),
    ) == "abnormal"


def test_custom_scenario_api_create_list_switch_and_delete_active() -> None:
    application = custom_app()
    with TestClient(application) as client:
        old_session = client.post("/api/session").json()["session_id"]
        created = client.post("/api/scenarios/custom", json=custom_payload())
        listed = client.get("/api/scenarios")
        switched = client.post("/api/scenarios/dns_lab")
        stale_after_switch = client.post(
            "/api/chat",
            json={"session_id": old_session, "message": "测试"},
        )
        active_session = switched.json()["session_id"]
        deleted = client.delete("/api/scenarios/custom/dns_lab")
        stale_after_delete = client.post(
            "/api/chat",
            json={"session_id": active_session, "message": "测试"},
        )

    assert created.status_code == 201
    assert created.json()["kind"] == "custom"
    assert created.json()["behavior"]["dns_resolved"] is False
    assert listed.json()["custom_count"] == 1
    assert listed.json()["custom_limit"] == 20
    assert any(item["name"] == "dns_lab" for item in listed.json()["scenarios"])
    assert switched.status_code == 200
    assert switched.json()["current"] == "dns_lab"
    assert stale_after_switch.status_code == 404
    assert deleted.status_code == 200
    assert deleted.json()["current"] == "healthy"
    assert deleted.json()["session_id"] is not None
    assert stale_after_delete.status_code == 404
    assert application.state.network_tools.provider.scenario_name == "healthy"


def test_custom_scenario_api_rejects_duplicates_limits_and_bad_payloads() -> None:
    with TestClient(custom_app(limit=1)) as client:
        first = client.post("/api/scenarios/custom", json=custom_payload("first_lab"))
        duplicate = client.post("/api/scenarios/custom", json=custom_payload("first_lab"))
        full = client.post("/api/scenarios/custom", json=custom_payload("second_lab"))
        built_in = client.post("/api/scenarios/custom", json=custom_payload("healthy"))
        invalid = client.post(
            "/api/scenarios/custom",
            json={**custom_payload("bad_lab"), "command": "whoami"},
        )
        missing = client.delete("/api/scenarios/custom/missing_lab")

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert full.status_code == 409
    assert built_in.status_code == 409
    assert invalid.status_code == 422
    assert missing.status_code == 404


@pytest.mark.parametrize(
    ("mode", "enabled", "expected"),
    [("mock", False, 403), ("local", True, 409)],
)
def test_custom_scenario_mutations_require_mock_mode_and_switch_flag(
    mode: str,
    enabled: bool,
    expected: int,
) -> None:
    with TestClient(custom_app(mode, enabled=enabled)) as client:
        created = client.post("/api/scenarios/custom", json=custom_payload())
        deleted = client.delete("/api/scenarios/custom/dns_lab")

    assert created.status_code == expected
    assert deleted.status_code == expected
