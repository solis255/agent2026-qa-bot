from __future__ import annotations

import inspect
import subprocess

import dns.resolver
import httpx
import pytest

from netpilot.tools import local_network
from netpilot.tools.local_network import LocalNetworkProvider, MAX_COMMAND_OUTPUT_CHARS
from netpilot.tools.mock_network import MockNetworkProvider
from netpilot.tools.schemas import ToolErrorCode


class PublicResolver:
    nameservers = ["1.1.1.1"]

    def resolve(self, domain: str, record_type: str, **kwargs: object) -> list[str]:
        if record_type == "A":
            return ["8.8.8.8"]
        raise dns.resolver.NoAnswer


class PrivateResolver(PublicResolver):
    def resolve(self, domain: str, record_type: str, **kwargs: object) -> list[str]:
        if record_type == "A":
            return ["127.0.0.1"]
        raise dns.resolver.NoAnswer


@pytest.mark.parametrize(
    "host",
    [
        "-n",
        "example.com;shutdown",
        "example.com && whoami",
        "example.com\nwhoami",
        "a" * 254,
        "bad..example.com",
    ],
)
def test_command_injection_hosts_are_rejected(host: str) -> None:
    result = MockNetworkProvider().ping_host(host)

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://[::1]/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/",
        "http://user:password@example.com/",
        "https://example.com/#fragment",
    ],
)
def test_unsafe_http_urls_are_rejected_before_execution(url: str) -> None:
    result = MockNetworkProvider().http_check(url)

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT


def test_domain_resolving_to_a_private_address_is_blocked() -> None:
    provider = LocalNetworkProvider(resolver=PrivateResolver())
    result = provider.http_check("https://example.com")

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT


def test_redirect_to_localhost_is_blocked_before_second_request() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    provider = LocalNetworkProvider(
        resolver=PublicResolver(),
        http_transport=httpx.MockTransport(handler),
    )
    result = provider.http_check("https://example.com")

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.INVALID_INPUT
    assert request_count == 1


def test_http_redirect_count_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path_number = int(request.url.path.strip("/") or "0")
        return httpx.Response(302, headers={"location": f"/{path_number + 1}"})

    provider = LocalNetworkProvider(
        resolver=PublicResolver(),
        http_transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(
        provider,
        "_assert_public_http_target",
        lambda url, **kwargs: None,
    )
    result = provider.http_check("https://example.com/0")

    assert result.success is False
    assert result.error is not None
    assert result.error.code is ToolErrorCode.REDIRECT_LIMIT


def test_http_timeout_is_captured_as_negative_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = LocalNetworkProvider(
        resolver=PublicResolver(),
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
    assert result.data.reachable is False
    assert result.data.failure_reason == "timeout"


def test_subprocess_calls_always_use_shell_false() -> None:
    calls: list[dict[str, object]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="")

    provider = LocalNetworkProvider(
        subprocess_runner=runner,
        resolver=PublicResolver(),
        system_name="windows",
    )
    provider.ping_host("example.com")
    provider.traceroute("example.com")

    assert calls
    assert all(call["shell"] is False for call in calls)
    assert "shell=True" not in inspect.getsource(local_network)


def test_command_output_is_capped() -> None:
    process = subprocess.CompletedProcess(
        ["ping"],
        0,
        stdout="x" * (MAX_COMMAND_OUTPUT_CHARS * 2),
        stderr="",
    )

    output = LocalNetworkProvider._combined_output(process)

    assert len(output) == MAX_COMMAND_OUTPUT_CHARS
