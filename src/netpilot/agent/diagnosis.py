"""Deterministic diagnosis built from typed tool evidence."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from netpilot.agent.evidence import finding_status, json_data
from netpilot.agent.schemas import AgentToolStep


@dataclass(frozen=True)
class DiagnosticAssessment:
    primary_issue: str
    confidence: str
    summary: str
    recommendations: tuple[str, ...]
    limitations: tuple[str, ...] = ()


def step_status(step: AgentToolStep) -> str:
    error_code = None
    if step.result.error is not None:
        error_code = str(
            getattr(step.result.error.code, "value", step.result.error.code)
        )
    return finding_status(
        step.tool_name,
        step.result.success,
        json_data(step.result.data),
        error_code,
    )


def assess_diagnosis(steps: list[AgentToolStep]) -> DiagnosticAssessment:
    """Classify evidence conservatively and return executable next actions."""

    by_tool = {step.tool_name: step for step in steps}
    statuses = {name: step_status(step) for name, step in by_tool.items()}
    limitations = tuple(_limitations(by_tool, statuses))

    fake_ip = _proxy_fake_ip(by_tool)
    http_blocked = statuses.get("http_check") == "blocked"
    if fake_ip and http_blocked:
        target = _target_label(by_tool)
        return DiagnosticAssessment(
            primary_issue="proxy_fake_ip_mapping",
            confidence="high",
            summary=(
                f"{target} 被解析到代理保留的 Fake-IP 地址，HTTP 安全策略因此未发送请求。"
                "这不能证明目标站点不可达，优先检查代理 DNS 与流量接管是否一致。"
            ),
            recommendations=(
                "如果准备使用代理，请启用代理客户端的 TUN/系统代理接管，并确认 DNS 与流量由同一客户端处理。",
                "如果已经关闭代理，请退出代理客户端及其 DNS 服务，恢复系统 DNS，然后执行 ipconfig /flushdns。",
                f"用 nslookup {target} 复查；结果不再位于 198.18.0.0/15 后，再重试 HTTPS 访问。",
            ),
            limitations=limitations,
        )

    if statuses.get("dns_lookup") == "abnormal":
        return DiagnosticAssessment(
            primary_issue="dns_resolution_failure",
            confidence="high",
            summary="目标域名没有得到可用地址，当前故障首先发生在 DNS 解析阶段。",
            recommendations=(
                "确认网卡 DNS 地址有效，并分别使用当前 DNS 与可信公共 DNS 执行 nslookup 对比。",
                "断开并重新连接校园网后刷新 DNS 缓存，再执行域名解析。",
                "若只有特定域名失败，记录 DNS 返回码并联系 DNS 或目标服务管理员。",
            ),
            limitations=limitations,
        )

    if statuses.get("get_network_info") == "abnormal":
        return DiagnosticAssessment(
            primary_issue="local_network_configuration",
            confidence="high",
            summary="本机缺少有效 IPv4 地址或默认网关，故障位于本地接入配置。",
            recommendations=(
                "重新连接 Wi-Fi 或网线，并确认网卡已获取 IPv4 地址、默认网关和 DNS。",
                "重新获取 DHCP 租约后先测试默认网关，再测试公网 IP。",
                "若仍无网关，请检查认证状态、VLAN 或联系校园网运维。",
            ),
            limitations=limitations,
        )

    if statuses.get("ping_host") == "abnormal":
        return DiagnosticAssessment(
            primary_issue="icmp_unreachable",
            confidence="medium",
            summary="目标没有返回 ICMP 响应；可能是路径中断，也可能是目标或防火墙禁用了 Ping。",
            recommendations=(
                "先 Ping 默认网关和 1.1.1.1，区分本地接入故障与公网路径问题。",
                "同时用 TCP 443 或 HTTPS 检测目标，避免仅凭 ICMP 无响应判定网站不可达。",
            ),
            limitations=limitations,
        )

    if statuses.get("tcp_check") == "abnormal":
        data = json_data(by_tool["tcp_check"].result.data) or {}
        reason = data.get("failure_reason") if isinstance(data, dict) else None
        detail = {
            "timeout": "TCP 连接在超时时间内没有建立，可能存在目标路径过滤或代理未接管。",
            "connection_refused": "目标主机明确拒绝了 TCP 连接，网络路径通常可达但端口未开放。",
            "dns_resolution_failed": "TCP 检测阶段无法解析目标域名。",
        }.get(reason, "目标 TCP 端口未能建立连接。")
        return DiagnosticAssessment(
            primary_issue="tcp_connectivity_failure",
            confidence="medium",
            summary=detail,
            recommendations=(
                "用同一目标的 TCP 443 与 HTTPS 结果交叉验证，并检查防火墙或代理是否覆盖该程序。",
                "若为 connection_refused，请确认目标端口和服务状态；若为 timeout，请对比其他公网目标。",
            ),
            limitations=limitations,
        )

    if statuses.get("http_check") == "abnormal":
        return DiagnosticAssessment(
            primary_issue="http_connectivity_failure",
            confidence="medium",
            summary="HTTP 检测已实际发送请求，但没有获得成功响应或状态码。",
            recommendations=(
                "检查系统代理、TLS 证书和目标 URL，并用浏览器与 curl 对比错误信息。",
                "若 TCP 443 正常而 HTTPS 失败，重点检查代理、TLS 握手和应用层策略。",
            ),
            limitations=limitations,
        )

    concrete_errors = [
        name for name, status in statuses.items() if status in {"error", "blocked"}
    ]
    inconclusive = [name for name, status in statuses.items() if status == "inconclusive"]
    if concrete_errors or inconclusive:
        return DiagnosticAssessment(
            primary_issue="insufficient_evidence",
            confidence="low",
            summary="部分检测被安全策略阻止、超时或执行失败，现有证据不能可靠定位网络故障。",
            recommendations=(
                "按检测结果中的限制说明修正目标或工具环境，再只重试失败的关键检测。",
                "至少保留一项公网 IP、DNS 和目标 TCP/HTTPS 证据后再作结论。",
            ),
            limitations=limitations,
        )

    if any(status == "normal" for status in statuses.values()):
        return DiagnosticAssessment(
            primary_issue="no_issue_observed",
            confidence="medium",
            summary="已执行的检测未发现明确异常。",
            recommendations=(
                "若问题仍存在，请补充具体目标、浏览器错误码、发生时间和是否启用代理后继续检测。",
            ),
            limitations=limitations,
        )

    return DiagnosticAssessment(
        primary_issue="undetermined",
        confidence="low",
        summary="尚无足够的网络检测证据。",
        recommendations=("请先执行与现象直接相关的网络检测。",),
        limitations=limitations,
    )


def build_diagnostic_answer(steps: list[AgentToolStep]) -> str:
    assessment = assess_diagnosis(steps)
    labels = {
        "get_network_info": "网络接口",
        "ping_host": "Ping 可达性",
        "dns_lookup": "DNS 解析",
        "tcp_check": "TCP 端口",
        "http_check": "HTTP 访问",
        "traceroute": "路由追踪",
        "knowledge_search": "校园网络知识检索",
    }
    markers = {
        "normal": "正常",
        "abnormal": "发现异常",
        "error": "执行失败",
        "inconclusive": "结果不确定",
        "blocked": "安全阻止",
        "reference": "参考资料",
    }
    evidence = [
        f"- {labels.get(step.tool_name, step.tool_name)}："
        f"{markers[step_status(step)]}，{step.result.summary}"
        for step in steps
    ]
    parts = [
        f"问题判断：{assessment.summary}",
        "检测结果：\n" + "\n".join(evidence),
        "建议操作：\n" + "\n".join(
            f"- {item}" for item in assessment.recommendations
        ),
    ]
    if assessment.limitations:
        parts.append(
            "结论限制：\n"
            + "\n".join(f"- {item}" for item in assessment.limitations)
        )
    return "\n\n".join(parts)


def _limitations(
    by_tool: dict[str, AgentToolStep], statuses: dict[str, str]
) -> list[str]:
    items: list[str] = []
    if statuses.get("ping_host") == "inconclusive":
        items.append("Ping 工具执行超时，不能据此判断目标可达或不可达。")
    if statuses.get("http_check") == "blocked":
        items.append("HTTP 请求在发送前被 SSRF 安全策略阻止，不代表网站返回了失败。")
    if statuses.get("knowledge_search") == "reference":
        items.append("知识库内容仅作操作参考，不是当前网络状态的检测证据。")
    for name, status in statuses.items():
        if status == "error" and name not in {"ping_host", "http_check"}:
            items.append(f"{name} 执行失败，本次结论未使用该项作为故障证据。")
    return items


def _proxy_fake_ip(by_tool: dict[str, AgentToolStep]) -> bool:
    addresses: list[str] = []
    for name in ("dns_lookup", "http_check"):
        step = by_tool.get(name)
        data = json_data(step.result.data) if step is not None else None
        if isinstance(data, dict):
            addresses.extend(data.get("addresses", []))
            addresses.extend(data.get("resolved_addresses", []))
    network = ipaddress.ip_network("198.18.0.0/15")
    for address in addresses:
        try:
            if ipaddress.ip_address(address) in network:
                return True
        except ValueError:
            continue
    return False


def _target_label(by_tool: dict[str, AgentToolStep]) -> str:
    for name, key in (("dns_lookup", "domain"), ("http_check", "url")):
        step = by_tool.get(name)
        value = step.arguments.get(key) if step is not None else None
        if isinstance(value, str) and value:
            if key == "url":
                return value.split("//", 1)[-1].split("/", 1)[0]
            return value
    return "目标域名"
