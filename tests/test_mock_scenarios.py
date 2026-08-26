from __future__ import annotations

import socket
import subprocess

import httpx
import pytest

from netpilot.config import MockScenario
from netpilot.tools.mock_network import MOCK_GATEWAY, MockNetworkProvider


@pytest.mark.parametrize("scenario", list(MockScenario))
def test_every_mock_scenario_runs_all_six_tools_offline(scenario: MockScenario) -> None:
    provider = MockNetworkProvider(scenario)
    results = [
        provider.get_network_info(),
        provider.ping_host("8.8.8.8"),
        provider.dns_lookup("example.com"),
        provider.tcp_check("example.com", 443),
        provider.http_check("https://example.com"),
        provider.traceroute("example.com"),
    ]

    assert len(results) == 6
    assert all(result.success for result in results)
    assert all(result.duration_ms < 1000 for result in results)


def test_mock_provider_never_calls_network_or_system_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("mock provider attempted external I/O")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    provider = MockNetworkProvider(MockScenario.HTTP_FAILURE)

    assert provider.get_network_info().success is True
    assert provider.ping_host("8.8.8.8").success is True
    assert provider.dns_lookup("example.com").success is True
    assert provider.tcp_check("example.com", 443).success is True
    assert provider.http_check("https://example.com").success is True
    assert provider.traceroute("example.com").success is True


def test_healthy_scenario_has_no_connectivity_failure() -> None:
    provider = MockNetworkProvider(MockScenario.HEALTHY)

    assert provider.ping_host("8.8.8.8").data.reachable is True
    assert provider.dns_lookup("example.com").data.resolved is True
    assert provider.tcp_check("example.com", 22).data.connected is True
    assert provider.http_check("https://example.com").data.reachable is True


def test_dns_failure_keeps_ip_connectivity_but_breaks_domain_resolution() -> None:
    provider = MockNetworkProvider(MockScenario.DNS_FAILURE)

    assert provider.ping_host("8.8.8.8").data.reachable is True
    assert provider.ping_host("example.com").data.reachable is False
    assert provider.dns_lookup("example.com").data.resolved is False
    assert provider.tcp_check("example.com", 443).data.connected is False


def test_gateway_unreachable_preserves_interface_configuration() -> None:
    provider = MockNetworkProvider(MockScenario.GATEWAY_UNREACHABLE)
    info = provider.get_network_info().data

    assert info.interfaces
    assert info.ipv4
    assert info.default_gateway == MOCK_GATEWAY
    assert provider.ping_host(MOCK_GATEWAY).data.reachable is False


def test_tcp_ssh_blocked_is_not_an_overall_outage() -> None:
    provider = MockNetworkProvider(MockScenario.TCP_SSH_BLOCKED)

    assert provider.dns_lookup("example.com").data.resolved is True
    assert provider.ping_host("example.com").data.reachable is True
    assert provider.tcp_check("example.com", 22).data.connected is False
    assert provider.tcp_check("example.com", 443).data.connected is True
    assert provider.http_check("https://example.com").data.reachable is True


def test_http_failure_keeps_dns_ping_and_tcp_443_healthy() -> None:
    provider = MockNetworkProvider(MockScenario.HTTP_FAILURE)

    assert provider.dns_lookup("example.com").data.resolved is True
    assert provider.ping_host("example.com").data.reachable is True
    assert provider.tcp_check("example.com", 443).data.connected is True
    assert provider.http_check("https://example.com").data.reachable is False


def test_partial_connectivity_contains_both_success_and_degradation() -> None:
    provider = MockNetworkProvider(MockScenario.PARTIAL_CONNECTIVITY)
    ping = provider.ping_host("example.com").data
    http = provider.http_check("https://example.com").data

    assert provider.dns_lookup("example.com").data.resolved is True
    assert ping.reachable is True and ping.packet_loss > 0
    assert provider.tcp_check("example.com", 443).data.connected is True
    assert provider.tcp_check("example.com", 22).data.connected is False
    assert http.reachable is True and http.status_code == 503


def test_mock_scenario_can_be_switched_deterministically() -> None:
    provider = MockNetworkProvider(MockScenario.HEALTHY)
    assert provider.dns_lookup("example.com").data.resolved is True

    selected = provider.set_scenario("dns_failure")

    assert selected is MockScenario.DNS_FAILURE
    assert provider.dns_lookup("example.com").data.resolved is False
