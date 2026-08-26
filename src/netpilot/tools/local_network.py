"""Cross-platform, read-only local network diagnostics."""

from __future__ import annotations

import ipaddress
import math
import platform
import re
import socket
import subprocess
from collections.abc import Callable
from time import perf_counter
from urllib.parse import urljoin, urlsplit

import dns.exception
import dns.resolver
import httpx
import psutil

from netpilot.tools.base import (
    NetworkProvider,
    ToolExecutionError,
    ToolObservation,
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
    ToolErrorCode,
    TraceHop,
    TracerouteData,
    TracerouteInput,
)
from netpilot.tools.validation import (
    UnsafeTargetError,
    assert_public_ip,
    validate_http_url,
)


MAX_COMMAND_OUTPUT_CHARS = 32_768
MAX_HTTP_HEADER_CHARS = 65_536
MAX_HTTP_REDIRECTS = 3


class LocalNetworkProvider(NetworkProvider):
    """Execute bounded diagnostics against the machine running NetPilot."""

    provider_name = "local"

    def __init__(
        self,
        timeout_seconds: float = 5.0,
        *,
        subprocess_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        resolver: dns.resolver.Resolver | None = None,
        http_transport: httpx.BaseTransport | None = None,
        system_name: str | None = None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self._subprocess_runner = subprocess_runner or subprocess.run
        self._resolver = resolver or dns.resolver.Resolver(configure=True)
        self._http_transport = http_transport
        self._system_name = (system_name or platform.system()).lower()

    def _get_network_info(
        self, request: GetNetworkInfoInput
    ) -> ToolObservation[NetworkInfoData]:
        del request
        address_map = psutil.net_if_addrs()
        stats_map = psutil.net_if_stats()
        interfaces: list[InterfaceInfo] = []
        all_ipv4: list[str] = []
        all_ipv6: list[str] = []

        for name in sorted(address_map):
            ipv4: list[str] = []
            ipv6: list[str] = []
            for address in address_map[name]:
                if address.family == socket.AF_INET:
                    ipv4.append(address.address)
                elif address.family == socket.AF_INET6:
                    ipv6.append(address.address.split("%", 1)[0])
            ipv4 = self._unique(ipv4)
            ipv6 = self._unique(ipv6)
            all_ipv4.extend(ipv4)
            all_ipv6.extend(ipv6)
            interfaces.append(
                InterfaceInfo(
                    name=name,
                    is_up=bool(stats_map.get(name) and stats_map[name].isup),
                    ipv4=ipv4,
                    ipv6=ipv6,
                )
            )

        gateway = self._get_default_gateway()
        dns_servers = self._get_dns_servers()
        return ToolObservation(
            "已获取本机网络接口、地址、默认网关和 DNS 配置",
            NetworkInfoData(
                interfaces=interfaces,
                ipv4=self._unique(all_ipv4),
                ipv6=self._unique(all_ipv6),
                default_gateway=gateway,
                dns_servers=dns_servers,
            ),
        )

    def _ping_host(self, request: PingHostInput) -> ToolObservation[PingData]:
        command = self._build_ping_command(request)
        completed = self._run_command(command)
        output = self._combined_output(completed)
        packet_loss = self._parse_packet_loss(output, completed.returncode)
        received = max(0, round(request.count * (100 - packet_loss) / 100))
        reachable = completed.returncode == 0 or received > 0
        average = self._parse_average_latency(output)
        data = PingData(
            reachable=reachable,
            packet_loss=packet_loss,
            avg_latency_ms=average,
            transmitted=request.count,
            received=received,
        )
        summary = "目标可达" if reachable else "目标不可达或未收到 ICMP 响应"
        return ToolObservation(summary, data)

    def _dns_lookup(self, request: DNSLookupInput) -> ToolObservation[DNSLookupData]:
        try:
            address = ipaddress.ip_address(request.domain)
            return ToolObservation(
                "输入已经是 IP 地址",
                DNSLookupData(resolved=True, addresses=[str(address)]),
            )
        except ValueError:
            pass

        addresses, state = self._resolve_records(request.domain)
        if state == "timeout":
            raise ToolExecutionError(
                ToolErrorCode.TIMEOUT,
                "DNS 查询超时",
            )
        if state == "error":
            raise ToolExecutionError(
                ToolErrorCode.DNS_ERROR,
                "DNS 查询执行失败",
            )
        if not addresses:
            return ToolObservation(
                "域名没有可用的 A 或 AAAA 记录",
                DNSLookupData(resolved=False, addresses=[]),
            )
        return ToolObservation(
            "域名解析成功",
            DNSLookupData(resolved=True, addresses=addresses),
        )

    def _tcp_check(self, request: TCPCheckInput) -> ToolObservation[TCPCheckData]:
        started = perf_counter()
        timeout = min(request.timeout, self.timeout_seconds, 10.0)
        try:
            connection = socket.create_connection(
                (request.host, request.port),
                timeout=timeout,
            )
            connection.close()
        except socket.gaierror:
            return self._tcp_negative("域名解析失败", "dns_resolution_failed")
        except (TimeoutError, socket.timeout):
            return self._tcp_negative("TCP 连接超时", "timeout")
        except ConnectionRefusedError:
            return self._tcp_negative("目标拒绝 TCP 连接", "connection_refused")
        except OSError:
            return self._tcp_negative("TCP 连接失败", "network_or_service_error")

        latency = round((perf_counter() - started) * 1000, 2)
        return ToolObservation(
            f"TCP/{request.port} 连接成功",
            TCPCheckData(connected=True, latency_ms=latency),
        )

    def _http_check(self, request: HTTPCheckInput) -> ToolObservation[HTTPCheckData]:
        started = perf_counter()
        current_url = request.url
        redirected = False
        timeout = httpx.Timeout(self.timeout_seconds)

        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            transport=self._http_transport,
            headers={"User-Agent": "TJU-NetPilot/0.1"},
        ) as client:
            for redirect_index in range(MAX_HTTP_REDIRECTS + 1):
                remaining = self.timeout_seconds - (perf_counter() - started)
                if remaining <= 0:
                    return self._http_negative(
                        current_url,
                        started,
                        redirected,
                        "HTTP 请求超时",
                        "timeout",
                    )
                self._assert_public_http_target(current_url, timeout_budget=remaining)
                remaining = self.timeout_seconds - (perf_counter() - started)
                if remaining <= 0:
                    return self._http_negative(
                        current_url,
                        started,
                        redirected,
                        "HTTP 请求超时",
                        "timeout",
                    )
                try:
                    with client.stream(
                        "GET",
                        current_url,
                        headers={"Range": "bytes=0-0"},
                        timeout=max(0.1, remaining),
                    ) as response:
                        status_code = response.status_code
                        location = response.headers.get("location")
                        header_size = sum(
                            len(name) + len(value)
                            for name, value in response.headers.multi_items()
                        )
                except httpx.TimeoutException:
                    return self._http_negative(
                        current_url,
                        started,
                        redirected,
                        "HTTP 请求超时",
                        "timeout",
                    )
                except httpx.RequestError:
                    return self._http_negative(
                        current_url,
                        started,
                        redirected,
                        "HTTP/TLS 连接失败",
                        "request_error",
                    )

                if header_size > MAX_HTTP_HEADER_CHARS:
                    raise ToolExecutionError(
                        ToolErrorCode.EXECUTION_ERROR,
                        "HTTP 响应头超过允许上限",
                    )

                if status_code in {301, 302, 303, 307, 308} and location:
                    if redirect_index >= MAX_HTTP_REDIRECTS:
                        raise ToolExecutionError(
                            ToolErrorCode.REDIRECT_LIMIT,
                            "HTTP 重定向次数超过上限",
                        )
                    redirected = True
                    try:
                        current_url = validate_http_url(urljoin(current_url, location))
                    except ValueError as exc:
                        raise ToolExecutionError(
                            ToolErrorCode.INVALID_INPUT,
                            "HTTP 重定向目标不安全或不合法",
                        ) from exc
                    continue

                elapsed = round((perf_counter() - started) * 1000, 2)
                return ToolObservation(
                    f"HTTP 请求已返回状态码 {status_code}",
                    HTTPCheckData(
                        reachable=True,
                        status_code=status_code,
                        elapsed_ms=elapsed,
                        redirected=redirected,
                        final_url=current_url,
                    ),
                )

        raise ToolExecutionError(
            ToolErrorCode.REDIRECT_LIMIT,
            "HTTP 重定向次数超过上限",
        )

    def _traceroute(self, request: TracerouteInput) -> ToolObservation[TracerouteData]:
        command = self._build_traceroute_command(request)
        try:
            completed = self._run_command(command, allow_missing=True)
        except FileNotFoundError as exc:
            raise ToolExecutionError(
                ToolErrorCode.UNSUPPORTED,
                "当前平台未安装 traceroute 工具",
                data=TracerouteData(supported=False),
            ) from exc

        output = self._combined_output(completed)
        hops = self._parse_traceroute_hops(output, request.max_hops)
        if not hops and completed.returncode != 0:
            raise ToolExecutionError(
                ToolErrorCode.EXECUTION_ERROR,
                "traceroute 执行失败或输出无法解析",
                data=TracerouteData(supported=True, reached_destination=False),
            )
        reached = bool(hops and not hops[-1].timed_out)
        return ToolObservation(
            "路由追踪已到达目标" if reached else "路由追踪未确认到达目标",
            TracerouteData(
                supported=True,
                reached_destination=reached,
                hops=hops,
            ),
        )

    def _get_default_gateway(self) -> str | None:
        if self._system_name == "windows":
            command = ["route", "print", "-4", "0.0.0.0"]
        elif self._system_name == "darwin":
            command = ["route", "-n", "get", "default"]
        else:
            command = ["ip", "-4", "route", "show", "default"]
        try:
            output = self._combined_output(self._run_command(command, allow_missing=True))
        except (FileNotFoundError, ToolExecutionError):
            return None

        if self._system_name == "windows":
            candidates: list[tuple[int, str]] = []
            for line in output.splitlines():
                match = re.match(
                    r"\s*0\.0\.0\.0\s+0\.0\.0\.0\s+((?:\d{1,3}\.){3}\d{1,3})"
                    r"\s+(?:\d{1,3}\.){3}\d{1,3}\s+(\d+)\s*$",
                    line,
                )
                if match:
                    candidates.append((int(match.group(2)), match.group(1)))
            return min(candidates)[1] if candidates else None
        if self._system_name == "darwin":
            match = re.search(r"^\s*gateway:\s*(\S+)", output, re.MULTILINE)
        else:
            match = re.search(r"\bdefault\s+via\s+(\S+)", output)
        return match.group(1) if match else None

    def _get_dns_servers(self) -> list[str]:
        servers: list[str] = []
        for value in getattr(self._resolver, "nameservers", []):
            try:
                servers.append(str(ipaddress.ip_address(str(value))))
            except ValueError:
                continue
        return self._unique(servers)

    def _resolve_records(
        self,
        domain: str,
        *,
        timeout_budget: float | None = None,
    ) -> tuple[list[str], str]:
        addresses: list[str] = []
        saw_timeout = False
        saw_error = False
        total_budget = min(timeout_budget or self.timeout_seconds, self.timeout_seconds)
        per_record_lifetime = max(0.1, total_budget / 2)
        for record_type in ("A", "AAAA"):
            try:
                answer = self._resolver.resolve(
                    domain,
                    record_type,
                    lifetime=per_record_lifetime,
                    search=False,
                )
                addresses.extend(str(item) for item in answer)
            except dns.resolver.NXDOMAIN:
                return [], "not_found"
            except dns.resolver.NoAnswer:
                continue
            except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
                saw_timeout = True
            except dns.exception.DNSException:
                saw_error = True
        if addresses:
            return self._unique(addresses), "resolved"
        if saw_timeout:
            return [], "timeout"
        if saw_error:
            return [], "error"
        return [], "not_found"

    def _assert_public_http_target(
        self,
        url: str,
        *,
        timeout_budget: float | None = None,
    ) -> None:
        host = urlsplit(url).hostname
        if not host:
            raise ToolExecutionError(ToolErrorCode.INVALID_INPUT, "HTTP URL 缺少目标主机")

        try:
            direct_address = ipaddress.ip_address(host)
            assert_public_ip(direct_address)
            return
        except UnsafeTargetError as exc:
            raise ToolExecutionError(
                ToolErrorCode.INVALID_INPUT,
                "HTTP 目标地址被安全策略阻止",
            ) from exc
        except ValueError:
            pass

        addresses, state = self._resolve_records(host, timeout_budget=timeout_budget)
        if state == "timeout":
            raise ToolExecutionError(ToolErrorCode.TIMEOUT, "HTTP 目标 DNS 查询超时")
        if not addresses:
            raise ToolExecutionError(ToolErrorCode.DNS_ERROR, "HTTP 目标无法解析")
        try:
            for address in addresses:
                assert_public_ip(ipaddress.ip_address(address))
        except (ValueError, UnsafeTargetError) as exc:
            raise ToolExecutionError(
                ToolErrorCode.INVALID_INPUT,
                "HTTP 目标解析到非公网地址，已阻止请求",
            ) from exc

    def _run_command(
        self,
        command: list[str],
        *,
        allow_missing: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._subprocess_runner(
                command,
                capture_output=True,
                text=True,
                errors="replace",
                shell=False,
                check=False,
                timeout=min(self.timeout_seconds + 1.0, 10.0),
            )
        except FileNotFoundError:
            if allow_missing:
                raise
            raise ToolExecutionError(
                ToolErrorCode.UNSUPPORTED,
                "当前平台缺少所需的系统网络工具",
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolExecutionError(
                ToolErrorCode.TIMEOUT,
                "系统网络工具执行超时",
            ) from exc

    def _build_ping_command(self, request: PingHostInput) -> list[str]:
        if self._system_name == "windows":
            per_reply_ms = max(250, round(self.timeout_seconds * 1000 / request.count))
            return [
                "ping",
                "-n",
                str(request.count),
                "-w",
                str(per_reply_ms),
                request.host,
            ]
        if self._system_name == "linux":
            per_reply_seconds = max(1, math.ceil(self.timeout_seconds / request.count))
            return [
                "ping",
                "-c",
                str(request.count),
                "-W",
                str(per_reply_seconds),
                request.host,
            ]
        return ["ping", "-c", str(request.count), request.host]

    def _build_traceroute_command(self, request: TracerouteInput) -> list[str]:
        if self._system_name == "windows":
            wait_ms = max(250, round(self.timeout_seconds * 1000 / request.max_hops))
            return [
                "tracert",
                "-d",
                "-h",
                str(request.max_hops),
                "-w",
                str(wait_ms),
                request.host,
            ]
        wait_seconds = max(1, math.ceil(self.timeout_seconds / request.max_hops))
        return [
            "traceroute",
            "-n",
            "-m",
            str(request.max_hops),
            "-w",
            str(wait_seconds),
            request.host,
        ]

    @staticmethod
    def _parse_packet_loss(output: str, returncode: int) -> float:
        percentages = re.findall(r"(\d+(?:\.\d+)?)\s*%", output)
        if percentages:
            return min(100.0, max(0.0, float(percentages[-1])))
        return 0.0 if returncode == 0 else 100.0

    @staticmethod
    def _parse_average_latency(output: str) -> float | None:
        average_match = re.search(
            r"(?:Average|平均)\s*=\s*<?\s*(\d+(?:\.\d+)?)\s*ms",
            output,
            re.IGNORECASE,
        )
        if average_match:
            return float(average_match.group(1))
        unix_match = re.search(
            r"=\s*\d+(?:\.\d+)?/(\d+(?:\.\d+)?)/\d+(?:\.\d+)?/",
            output,
        )
        if unix_match:
            return float(unix_match.group(1))
        samples = re.findall(
            r"(?:time|时间)[=<]\s*(\d+(?:\.\d+)?)\s*ms",
            output,
            re.IGNORECASE,
        )
        if samples:
            values = [float(sample) for sample in samples]
            return round(sum(values) / len(values), 2)
        return None

    @staticmethod
    def _parse_traceroute_hops(output: str, max_hops: int) -> list[TraceHop]:
        hops: list[TraceHop] = []
        address_pattern = re.compile(
            r"(?<![\w:])((?:\d{1,3}\.){3}\d{1,3})(?![\w:])"
            r"|(?<![\w:])([0-9A-Fa-f]*:[0-9A-Fa-f:]+)(?![\w:])"
        )
        for line in output.splitlines():
            hop_match = re.match(r"^\s*(\d+)\s+(.+)$", line)
            if not hop_match:
                continue
            hop_number = int(hop_match.group(1))
            if not 1 <= hop_number <= max_hops:
                continue
            remainder = hop_match.group(2)
            address: str | None = None
            for candidate_match in address_pattern.finditer(remainder):
                candidate = candidate_match.group(1) or candidate_match.group(2)
                try:
                    address = str(ipaddress.ip_address(candidate))
                    break
                except ValueError:
                    continue
            latencies = re.findall(r"<?\s*(\d+(?:\.\d+)?)\s*ms", remainder, re.IGNORECASE)
            latency = float(latencies[0]) if latencies else None
            hops.append(
                TraceHop(
                    hop=hop_number,
                    address=address,
                    latency_ms=latency,
                    timed_out=address is None and "*" in remainder,
                )
            )
        return hops

    @staticmethod
    def _combined_output(completed: subprocess.CompletedProcess[str]) -> str:
        output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        return output[:MAX_COMMAND_OUTPUT_CHARS]

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _tcp_negative(summary: str, reason: str) -> ToolObservation[TCPCheckData]:
        return ToolObservation(
            summary,
            TCPCheckData(connected=False, latency_ms=None, failure_reason=reason),
        )

    @staticmethod
    def _http_negative(
        url: str,
        started: float,
        redirected: bool,
        summary: str,
        reason: str,
    ) -> ToolObservation[HTTPCheckData]:
        return ToolObservation(
            summary,
            HTTPCheckData(
                reachable=False,
                status_code=None,
                elapsed_ms=round((perf_counter() - started) * 1000, 2),
                redirected=redirected,
                final_url=url,
                failure_reason=reason,
            ),
        )
