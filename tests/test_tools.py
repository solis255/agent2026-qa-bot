from __future__ import annotations

import socket
import subprocess
from types import SimpleNamespace

import dns.resolver
import httpx
import pytest

from netpilot.tools.local_network import LocalNetworkProvider
from netpilot.tools.mock_network import MockNetworkProvider
from netpilot.tools.schemas import ToolErrorCode
from netpilot.tools.service import build_network_tools
from netpilot.config import Settings


class FakeResolver:
    nameservers = ["1.1.1.1"]

    def resolve(
        self,
        domain: str,
        record_type: str,
        *,
        lifetime: float,
        search: bool,
    ) -> list[str]:
        assert domain == "example.com"
        assert lifetime > 0
        assert search is False
        if record_type == "A":
            return ["93.184.216.34"]
        raise dns.resolver.NoAnswer


def completed(command: list[str], stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


def test_mock_tools_share_the_uniform_result_envelope() -> None:
    provider = MockNetworkProvider()
    results = [
        provider.get_network_info(),
        provider.ping_host("8.8.8.8"),
        provider.dns_lookup("example.com"),
        provider.tcp_check("example.com", 443),
        provider.http_check("https://example.com"),
        provider.traceroute("example.com"),
    ]

    assert {result.tool for result in results} == {
        "get_network_info",
        "ping_host",
        "dns_lookup",
        "tcp_check",
        "http_check",
        "traceroute",
    }
    for result in results:
        assert result.success is True
        assert result.data is not None
        assert result.error is None
        assert result.duration_ms >= 0
        payload = result.model_dump(mode="json")
        assert set(payload) == {
            "success",
            "tool",
            "summary",
            "data",
            "error",
            "duration_ms",
        }


@pytest.mark.parametrize(
    ("method", "arguments"),
    [
        ("ping_host", ("; shutdown", 3)),
        ("ping_host", ("example.com", 0)),
        ("dns_lookup", ("bad host",)),
        ("tcp_check", ("example.com", 0, 3)),
        ("tcp_check", ("example.com", 443, 11)),
        ("http_check", ("file:///etc/passwd",)),
        ("traceroute", ("example.com", 31)),
    ],
)
def test_invalid_tool_input_returns_a_safe_failure(method: str, arguments: tuple[object, ...]) -> None:
    result = getattr(MockNetworkProvider(), method)(*arguments)

    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert "shutdown" not in result.summary


def test_local_get_network_info_omits_link_layer_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    addresses = {
        "Ethernet": [
            SimpleNamespace(family=socket.AF_INET, address="192.168.1.20"),
            SimpleNamespace(family=socket.AF_INET6, address="2001:db8::20%4"),
            SimpleNamespace(family=psutil_af_link(), address="00:11:22:33:44:55"),
        ]
    }
    stats = {"Ethernet": SimpleNamespace(isup=True)}
    monkeypatch.setattr("netpilot.tools.local_network.psutil.net_if_addrs", lambda: addresses)
    monkeypatch.setattr("netpilot.tools.local_network.psutil.net_if_stats", lambda: stats)

    def route_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == ["route", "print", "-4", "0.0.0.0"]
        assert kwargs["shell"] is False
        return completed(
            command,
            "0.0.0.0          0.0.0.0      192.168.1.1    192.168.1.20     25",
        )

    provider = LocalNetworkProvider(
        subprocess_runner=route_runner,
        resolver=FakeResolver(),
        system_name="windows",
    )
    result = provider.get_network_info()

    assert result.success is True
    assert result.data is not None
    assert result.data.default_gateway == "192.168.1.1"
    assert result.data.dns_servers == ["1.1.1.1"]
    assert result.data.ipv4 == ["192.168.1.20"]
    assert result.data.ipv6 == ["2001:db8::20"]
    assert "00:11:22:33:44:55" not in result.model_dump_json()


def psutil_af_link() -> object:
    import psutil

    return psutil.AF_LINK


def test_local_ping_uses_a_bounded_argument_list() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return completed(
            command,
            "Packets: Sent = 3, Received = 3, Lost = 0 (0% loss)\n"
            "Minimum = 10ms, Maximum = 14ms, Average = 12ms",
        )

    provider = LocalNetworkProvider(
        timeout_seconds=5,
        subprocess_runner=runner,
        resolver=FakeResolver(),
        system_name="windows",
    )
    result = provider.ping_host("example.com", 3)

    assert result.success is True
    assert result.data is not None
    assert result.data.reachable is True
    assert result.data.packet_loss == 0
    assert result.data.avg_latency_ms == 12
    command, kwargs = calls[0]
    assert command[0] == "ping"
    assert command[-1] == "example.com"
    assert kwargs["shell"] is False
    assert kwargs["timeout"] <= 10


def test_local_command_timeout_is_captured() -> None:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=float(kwargs["timeout"]))

    provider = LocalNetworkProvider(
        subprocess_runner=runner,
        resolver=FakeResolver(),
        system_name="windows",
    )
    result = provider.ping_host("example.com")

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.TIMEOUT


def test_local_ping_parses_localized_windows_output() -> None:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed(
            command,
            "数据包: 已发送 = 3，已接收 = 2，丢失 = 1 (33% 丢失)\n"
            "最短 = 10ms，最长 = 20ms，平均 = 15ms",
        )

    result = LocalNetworkProvider(
        subprocess_runner=runner,
        resolver=FakeResolver(),
        system_name="windows",
    ).ping_host("example.com")

    assert result.success is True
    assert result.data is not None
    assert result.data.packet_loss == 33
    assert result.data.avg_latency_ms == 15


def test_local_ping_parses_unix_output() -> None:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed(
            command,
            "3 packets transmitted, 3 received, 0% packet loss\n"
            "rtt min/avg/max/mdev = 10.000/12.500/14.000/1.000 ms",
        )

    result = LocalNetworkProvider(
        subprocess_runner=runner,
        resolver=FakeResolver(),
        system_name="linux",
    ).ping_host("example.com")

    assert result.success is True
    assert result.data is not None
    assert result.data.packet_loss == 0
    assert result.data.avg_latency_ms == 12.5


def test_local_dns_lookup_uses_the_bounded_resolver() -> None:
    result = LocalNetworkProvider(resolver=FakeResolver()).dns_lookup("example.com")

    assert result.success is True
    assert result.data is not None
    assert result.data.resolved is True
    assert result.data.addresses == ["93.184.216.34"]


def test_local_tcp_check_closes_the_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket = SimpleNamespace(closed=False)

    def close() -> None:
        fake_socket.closed = True

    fake_socket.close = close

    def create_connection(address: tuple[str, int], timeout: float) -> object:
        assert address == ("example.com", 443)
        assert timeout == 3
        return fake_socket

    monkeypatch.setattr("netpilot.tools.local_network.socket.create_connection", create_connection)
    result = LocalNetworkProvider(resolver=FakeResolver()).tcp_check("example.com", 443)

    assert result.success is True
    assert result.data is not None and result.data.connected is True
    assert fake_socket.closed is True


def test_local_tcp_negative_result_is_diagnostic_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(address: tuple[str, int], timeout: float) -> object:
        raise ConnectionRefusedError

    monkeypatch.setattr("netpilot.tools.local_network.socket.create_connection", refuse)
    result = LocalNetworkProvider(resolver=FakeResolver()).tcp_check("example.com", 22)

    assert result.success is True
    assert result.data is not None and result.data.connected is False
    assert result.data.failure_reason == "connection_refused"
    assert result.error is None


def test_local_http_check_follows_a_bounded_safe_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/health"})
        return httpx.Response(204)

    provider = LocalNetworkProvider(
        resolver=FakeResolver(),
        http_transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(
        provider,
        "_assert_public_http_target",
        lambda url, **kwargs: None,
    )
    result = provider.http_check("https://example.com")

    assert result.success is True
    assert result.data is not None
    assert result.data.reachable is True
    assert result.data.status_code == 204
    assert result.data.redirected is True
    assert result.data.final_url == "https://example.com/health"


def test_local_traceroute_parses_hops() -> None:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed(
            command,
            "  1     1 ms     1 ms     1 ms  192.168.1.1\n"
            "  2    12 ms    11 ms    10 ms  93.184.216.34",
        )

    provider = LocalNetworkProvider(
        subprocess_runner=runner,
        resolver=FakeResolver(),
        system_name="windows",
    )
    result = provider.traceroute("example.com")

    assert result.success is True
    assert result.data is not None
    assert result.data.reached_destination is True
    assert [hop.address for hop in result.data.hops] == ["192.168.1.1", "93.184.216.34"]


def test_local_traceroute_gracefully_reports_unsupported() -> None:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    result = LocalNetworkProvider(
        subprocess_runner=runner,
        resolver=FakeResolver(),
        system_name="linux",
    ).traceroute("example.com")

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.UNSUPPORTED
    assert result.data is not None and result.data.supported is False


@pytest.mark.parametrize(
    ("system_name", "ping_executable", "trace_executable"),
    [
        ("windows", "ping", "tracert"),
        ("linux", "ping", "traceroute"),
        ("darwin", "ping", "traceroute"),
    ],
)
def test_local_provider_builds_platform_specific_fixed_commands(
    system_name: str,
    ping_executable: str,
    trace_executable: str,
) -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[0] == ping_executable:
            return completed(command, "0% packet loss")
        return completed(command, " 1  8.8.8.8  1 ms")

    provider = LocalNetworkProvider(
        subprocess_runner=runner,
        resolver=FakeResolver(),
        system_name=system_name,
    )
    provider.ping_host("8.8.8.8")
    provider.traceroute("8.8.8.8")

    assert commands[0][0] == ping_executable
    assert commands[1][0] == trace_executable
    assert all(isinstance(argument, str) for command in commands for argument in command)


def test_unexpected_provider_exception_does_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "netpilot.tools.local_network.psutil.net_if_addrs",
        lambda: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    result = LocalNetworkProvider(resolver=FakeResolver()).get_network_info()

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.EXECUTION_ERROR
    assert "unexpected" not in result.error.message


def test_application_settings_select_the_provider_without_running_a_check() -> None:
    mock_service = build_network_tools(
        Settings(_env_file=None, tool_mode="mock", mock_scenario="http_failure")
    )
    local_service = build_network_tools(Settings(_env_file=None, tool_mode="local"))

    assert mock_service.provider_name == "mock"
    assert mock_service.provider.scenario.value == "http_failure"
    assert local_service.provider_name == "local"
