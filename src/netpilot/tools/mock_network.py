"""Deterministic, fully offline network provider for demos and tests."""

from __future__ import annotations

import ipaddress
from threading import RLock

from netpilot.config import MockScenario
from netpilot.tools.base import NetworkProvider, ToolObservation
from netpilot.tools.custom_scenarios import (
    CustomMockScenario,
    CustomScenarioExistsError,
    CustomScenarioLimitError,
    CustomScenarioNotFoundError,
)
from netpilot.tools.schemas import (
    DNSLookupData,
    DNSLookupInput,
    GetNetworkInfoInput,
    HTTPCheckData,
    HTTPCheckInput,
    InterfaceInfo,
    NetworkInfoData,
    PingData,
    PingHostInput,
    TCPCheckData,
    TCPCheckInput,
    TraceHop,
    TracerouteData,
    TracerouteInput,
)


MOCK_IPV4 = "192.168.10.20"
MOCK_GATEWAY = "192.168.10.1"
MOCK_DNS = "223.5.5.5"
MOCK_PUBLIC_ADDRESS = "93.184.216.34"


class MockNetworkProvider(NetworkProvider):
    """End-user connectivity scenarios independent of the upstream topology."""

    provider_name = "mock"

    def __init__(
        self,
        scenario: MockScenario | str = MockScenario.HEALTHY,
        timeout_seconds: float = 5.0,
        max_custom_scenarios: int = 20,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self._lock = RLock()
        self._scenario = MockScenario(scenario)
        self._custom_scenarios: dict[str, CustomMockScenario] = {}
        self._max_custom_scenarios = max(1, min(int(max_custom_scenarios), 100))

    @property
    def scenario(self) -> MockScenario | str:
        with self._lock:
            return self._scenario

    @property
    def scenario_name(self) -> str:
        current = self.scenario
        return current.value if isinstance(current, MockScenario) else current

    @property
    def max_custom_scenarios(self) -> int:
        return self._max_custom_scenarios

    def set_scenario(self, scenario: MockScenario | str) -> MockScenario | str:
        value = scenario.value if isinstance(scenario, MockScenario) else str(scenario)
        with self._lock:
            try:
                validated: MockScenario | str = MockScenario(value)
            except ValueError:
                if value not in self._custom_scenarios:
                    raise CustomScenarioNotFoundError("自定义 Mock 场景不存在")
                validated = value
            self._scenario = validated
            return validated

    def list_custom_scenarios(self) -> list[CustomMockScenario]:
        with self._lock:
            return list(self._custom_scenarios.values())

    def add_custom_scenario(self, scenario: CustomMockScenario) -> CustomMockScenario:
        with self._lock:
            if scenario.name in {item.value for item in MockScenario}:
                raise CustomScenarioExistsError("不能覆盖内置 Mock 场景")
            if scenario.name in self._custom_scenarios:
                raise CustomScenarioExistsError("自定义 Mock 场景名称已存在")
            if len(self._custom_scenarios) >= self._max_custom_scenarios:
                raise CustomScenarioLimitError("自定义 Mock 场景数量已达到上限")
            self._custom_scenarios[scenario.name] = scenario
            return scenario

    def delete_custom_scenario(self, name: str) -> bool:
        """Delete one definition and safely fall back if it was active."""

        with self._lock:
            if name not in self._custom_scenarios:
                raise CustomScenarioNotFoundError("自定义 Mock 场景不存在")
            was_active = self._scenario == name
            del self._custom_scenarios[name]
            if was_active:
                self._scenario = MockScenario.HEALTHY
            return was_active

    def _active_custom(self) -> CustomMockScenario | None:
        with self._lock:
            if isinstance(self._scenario, str):
                return self._custom_scenarios.get(self._scenario)
            return None

    def _get_network_info(
        self, request: GetNetworkInfoInput
    ) -> ToolObservation[NetworkInfoData]:
        del request
        custom = self._active_custom()
        if custom is not None:
            configured = custom.behavior.network_configured
            interface = InterfaceInfo(
                name="mock-custom0",
                is_up=configured,
                ipv4=[MOCK_IPV4] if configured else [],
                ipv6=["2001:db8:2026::20"] if configured else [],
            )
            return ToolObservation(
                "自定义场景：本机网络配置完整" if configured else "自定义场景：本机缺少有效网络配置",
                NetworkInfoData(
                    interfaces=[interface],
                    ipv4=list(interface.ipv4),
                    ipv6=list(interface.ipv6),
                    default_gateway=MOCK_GATEWAY if configured else None,
                    dns_servers=[MOCK_DNS] if configured else [],
                ),
            )
        scenario = self.scenario
        interface = InterfaceInfo(
            name="mock-wifi0",
            is_up=True,
            ipv4=[MOCK_IPV4],
            ipv6=["2001:db8:2026::20"],
        )
        data = NetworkInfoData(
            interfaces=[interface],
            ipv4=list(interface.ipv4),
            ipv6=list(interface.ipv6),
            default_gateway=MOCK_GATEWAY,
            dns_servers=[MOCK_DNS],
        )
        if scenario is MockScenario.GATEWAY_UNREACHABLE:
            summary = "网络接口和 IP 已配置，但默认网关不可达"
        else:
            summary = "网络接口、IP、默认网关和 DNS 配置已获取"
        return ToolObservation(summary, data)

    def _ping_host(self, request: PingHostInput) -> ToolObservation[PingData]:
        custom = self._active_custom()
        if custom is not None:
            behavior = custom.behavior
            if not behavior.ping_reachable:
                return self._ping_unreachable(request, "自定义场景：目标不可达")
            received = max(
                1,
                min(
                    request.count,
                    round(request.count * (100 - behavior.ping_packet_loss_percent) / 100),
                ),
            )
            return ToolObservation(
                "自定义场景：目标可达"
                if behavior.ping_packet_loss_percent == 0
                else "自定义场景：目标可达但存在丢包",
                PingData(
                    reachable=True,
                    packet_loss=behavior.ping_packet_loss_percent,
                    avg_latency_ms=48.0,
                    transmitted=request.count,
                    received=received,
                ),
            )
        scenario = self.scenario
        is_ip = self._is_ip(request.host)

        if scenario is MockScenario.GATEWAY_UNREACHABLE:
            return self._ping_unreachable(request, "目标不可达，本地网关可能异常")
        if scenario is MockScenario.DNS_FAILURE and not is_ip:
            return self._ping_unreachable(request, "域名无法解析，未执行有效 ICMP 检测")
        if scenario is MockScenario.PARTIAL_CONNECTIVITY:
            received = max(1, round(request.count / 2))
            loss = round((request.count - received) / request.count * 100, 1)
            return ToolObservation(
                "目标可达，但检测到明显丢包",
                PingData(
                    reachable=True,
                    packet_loss=loss,
                    avg_latency_ms=86.0,
                    transmitted=request.count,
                    received=received,
                ),
            )

        return ToolObservation(
            "目标可达，ICMP 检测正常",
            PingData(
                reachable=True,
                packet_loss=0,
                avg_latency_ms=12.0,
                transmitted=request.count,
                received=request.count,
            ),
        )

    def _dns_lookup(self, request: DNSLookupInput) -> ToolObservation[DNSLookupData]:
        if self._is_ip(request.domain):
            return ToolObservation(
                "输入已经是 IP 地址",
                DNSLookupData(resolved=True, addresses=[request.domain]),
            )
        custom = self._active_custom()
        if custom is not None:
            resolved = custom.behavior.dns_resolved
            return ToolObservation(
                "自定义场景：域名解析成功" if resolved else "自定义场景：域名解析失败",
                DNSLookupData(
                    resolved=resolved,
                    addresses=[MOCK_PUBLIC_ADDRESS] if resolved else [],
                ),
            )
        if self.scenario is MockScenario.DNS_FAILURE:
            return ToolObservation(
                "域名解析失败",
                DNSLookupData(resolved=False, addresses=[]),
            )
        if self.scenario is MockScenario.GATEWAY_UNREACHABLE:
            return ToolObservation(
                "由于接入网络异常，域名解析不可用",
                DNSLookupData(resolved=False, addresses=[]),
            )
        return ToolObservation(
            "域名解析成功",
            DNSLookupData(resolved=True, addresses=[MOCK_PUBLIC_ADDRESS]),
        )

    def _tcp_check(self, request: TCPCheckInput) -> ToolObservation[TCPCheckData]:
        custom = self._active_custom()
        if custom is not None:
            if not custom.behavior.tcp_connected:
                return self._tcp_unavailable(
                    f"自定义场景：TCP/{request.port} 连接失败",
                    "custom_scenario_unavailable",
                )
            return ToolObservation(
                f"自定义场景：TCP/{request.port} 连接成功",
                TCPCheckData(connected=True, latency_ms=36.0),
            )
        scenario = self.scenario
        if scenario is MockScenario.GATEWAY_UNREACHABLE:
            return self._tcp_unavailable("本地网关不可达，无法建立 TCP 连接", "network_unreachable")
        if scenario is MockScenario.DNS_FAILURE and not self._is_ip(request.host):
            return self._tcp_unavailable("域名解析失败，无法建立 TCP 连接", "dns_resolution_failed")
        if scenario is MockScenario.TCP_SSH_BLOCKED and request.port == 22:
            return self._tcp_unavailable("TCP/22 连接超时", "port_blocked_or_service_unavailable")
        if scenario is MockScenario.PARTIAL_CONNECTIVITY and request.port == 22:
            return self._tcp_unavailable("部分连接受限，TCP/22 不可用", "partial_connectivity")
        return ToolObservation(
            f"TCP/{request.port} 连接成功",
            TCPCheckData(connected=True, latency_ms=18.0),
        )

    def _http_check(self, request: HTTPCheckInput) -> ToolObservation[HTTPCheckData]:
        custom = self._active_custom()
        if custom is not None:
            behavior = custom.behavior
            if not behavior.http_reachable:
                return ToolObservation(
                    "自定义场景：HTTP 请求已发送但未获得响应",
                    HTTPCheckData(
                        reachable=False,
                        status_code=None,
                        elapsed_ms=None,
                        redirected=False,
                        final_url=request.url,
                        failure_reason="custom_scenario_unavailable",
                        request_sent=True,
                        resolved_addresses=[MOCK_PUBLIC_ADDRESS],
                    ),
                )
            return ToolObservation(
                f"自定义场景：HTTP 服务返回 {behavior.http_status_code}",
                HTTPCheckData(
                    reachable=True,
                    status_code=behavior.http_status_code,
                    elapsed_ms=75.0,
                    redirected=False,
                    final_url=request.url,
                    request_sent=True,
                    resolved_addresses=[MOCK_PUBLIC_ADDRESS],
                ),
            )
        scenario = self.scenario
        if scenario is MockScenario.GATEWAY_UNREACHABLE:
            return self._http_unavailable(
                request.url,
                "本地网关不可达",
                "network_unreachable",
            )
        if scenario is MockScenario.DNS_FAILURE:
            return self._http_unavailable(
                request.url,
                "域名解析失败",
                "dns_resolution_failed",
            )
        if scenario is MockScenario.HTTP_FAILURE:
            return self._http_unavailable(
                request.url,
                "HTTP/TLS 或应用服务异常",
                "http_tls_or_application_failure",
            )
        if scenario is MockScenario.PARTIAL_CONNECTIVITY:
            return ToolObservation(
                "HTTP 服务可连接，但返回临时不可用状态",
                HTTPCheckData(
                    reachable=True,
                    status_code=503,
                    elapsed_ms=240.0,
                    redirected=False,
                    final_url=request.url,
                    failure_reason="service_unavailable",
                ),
            )
        return ToolObservation(
            "HTTP/HTTPS 访问正常",
            HTTPCheckData(
                reachable=True,
                status_code=200,
                elapsed_ms=42.0,
                redirected=False,
                final_url=request.url,
            ),
        )

    def _traceroute(self, request: TracerouteInput) -> ToolObservation[TracerouteData]:
        custom = self._active_custom()
        if custom is not None:
            hops = [TraceHop(hop=1, address=MOCK_GATEWAY, latency_ms=1.0)]
            if custom.behavior.traceroute_reached:
                hops.append(TraceHop(hop=2, address=MOCK_PUBLIC_ADDRESS, latency_ms=42.0))
                summary = "自定义场景：路由追踪已到达目标"
            else:
                hops.append(TraceHop(hop=2, timed_out=True))
                summary = "自定义场景：路由追踪未到达目标"
            selected_hops = hops[: request.max_hops]
            return ToolObservation(
                summary,
                TracerouteData(
                    reached_destination=bool(
                        custom.behavior.traceroute_reached
                        and selected_hops
                        and selected_hops[-1].address == MOCK_PUBLIC_ADDRESS
                    ),
                    hops=selected_hops,
                ),
            )
        scenario = self.scenario
        if scenario is MockScenario.GATEWAY_UNREACHABLE:
            return ToolObservation(
                "路由追踪在第一跳超时",
                TracerouteData(
                    reached_destination=False,
                    hops=[TraceHop(hop=1, timed_out=True)],
                ),
            )
        if scenario is MockScenario.DNS_FAILURE and not self._is_ip(request.host):
            return ToolObservation(
                "目标域名无法解析，未获得路由跳点",
                TracerouteData(reached_destination=False, hops=[]),
            )

        hops = [
            TraceHop(hop=1, address=MOCK_GATEWAY, latency_ms=1.0),
            TraceHop(hop=2, address="198.51.100.1", latency_ms=8.0),
        ]
        if scenario is MockScenario.PARTIAL_CONNECTIVITY:
            hops.append(TraceHop(hop=3, timed_out=True))
            hops.append(TraceHop(hop=4, address=MOCK_PUBLIC_ADDRESS, latency_ms=91.0))
            summary = "路由可到达目标，但中间跳点存在超时和高延迟"
        else:
            hops.append(TraceHop(hop=3, address=MOCK_PUBLIC_ADDRESS, latency_ms=16.0))
            summary = "路由追踪已到达目标"
        selected_hops = hops[: request.max_hops]
        reached_destination = bool(
            selected_hops and selected_hops[-1].address == MOCK_PUBLIC_ADDRESS
        )
        return ToolObservation(
            summary,
            TracerouteData(
                reached_destination=reached_destination,
                hops=selected_hops,
            ),
        )

    @staticmethod
    def _is_ip(host: str) -> bool:
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    @staticmethod
    def _ping_unreachable(request: PingHostInput, summary: str) -> ToolObservation[PingData]:
        return ToolObservation(
            summary,
            PingData(
                reachable=False,
                packet_loss=100,
                avg_latency_ms=None,
                transmitted=request.count,
                received=0,
            ),
        )

    @staticmethod
    def _tcp_unavailable(summary: str, reason: str) -> ToolObservation[TCPCheckData]:
        return ToolObservation(
            summary,
            TCPCheckData(connected=False, latency_ms=None, failure_reason=reason),
        )

    @staticmethod
    def _http_unavailable(
        url: str,
        summary: str,
        reason: str,
    ) -> ToolObservation[HTTPCheckData]:
        return ToolObservation(
            summary,
            HTTPCheckData(
                reachable=False,
                status_code=None,
                elapsed_ms=None,
                redirected=False,
                final_url=url,
                failure_reason=reason,
            ),
        )
