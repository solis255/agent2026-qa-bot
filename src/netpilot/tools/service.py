"""Configured facade for selecting and invoking a network provider."""

from __future__ import annotations

from netpilot.config import MockScenario, Settings, ToolMode
from netpilot.tools.base import NetworkProvider
from netpilot.tools.schemas import (
    DNSLookupData,
    HTTPCheckData,
    NetworkInfoData,
    PingData,
    TCPCheckData,
    ToolResult,
    TracerouteData,
)


class NetworkToolService:
    """Stable delegation surface used by the future ToolRegistry."""

    def __init__(self, provider: NetworkProvider) -> None:
        self.provider = provider

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    def get_network_info(self) -> ToolResult[NetworkInfoData]:
        return self.provider.get_network_info()

    def ping_host(self, host: str, count: int = 3) -> ToolResult[PingData]:
        return self.provider.ping_host(host, count)

    def dns_lookup(self, domain: str) -> ToolResult[DNSLookupData]:
        return self.provider.dns_lookup(domain)

    def tcp_check(
        self,
        host: str,
        port: int,
        timeout: float = 3.0,
    ) -> ToolResult[TCPCheckData]:
        return self.provider.tcp_check(host, port, timeout)

    def http_check(self, url: str) -> ToolResult[HTTPCheckData]:
        return self.provider.http_check(url)

    def traceroute(self, host: str, max_hops: int = 15) -> ToolResult[TracerouteData]:
        return self.provider.traceroute(host, max_hops)

    def set_mock_scenario(self, scenario: MockScenario | str) -> MockScenario:
        """Switch an existing mock provider without exposing an HTTP route yet."""

        from netpilot.tools.mock_network import MockNetworkProvider

        if not isinstance(self.provider, MockNetworkProvider):
            raise RuntimeError("scenario switching is only available in mock mode")
        return self.provider.set_scenario(scenario)


def build_network_tools(settings: Settings) -> NetworkToolService:
    """Create the configured provider without running a network check."""

    if settings.tool_mode is ToolMode.MOCK:
        from netpilot.tools.mock_network import MockNetworkProvider

        provider: NetworkProvider = MockNetworkProvider(
            scenario=settings.mock_scenario,
            timeout_seconds=settings.network_timeout_seconds,
        )
    else:
        from netpilot.tools.local_network import LocalNetworkProvider

        provider = LocalNetworkProvider(
            timeout_seconds=settings.network_timeout_seconds,
        )
    return NetworkToolService(provider)
