"""Coverage and evidence-sufficiency models for bounded diagnosis turns."""

from __future__ import annotations

import ipaddress
from enum import Enum
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from netpilot.agent.evidence import finding_status, json_data


class DiagnosticGoal(str, Enum):
    FULL_WEB_DIAGNOSIS = "full_web_diagnosis"
    WEB_UNREACHABLE = "web_unreachable"
    DNS_CHECK = "dns_check"
    TCP_CHECK = "tcp_check"
    GENERIC_DIAGNOSIS = "generic_diagnosis"
    NON_DIAGNOSTIC = "non_diagnostic"


class DiagnosticCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network_config_checked: bool = False
    gateway_checked: bool = False
    dns_checked: bool = False
    ip_connectivity_checked: bool = False
    tcp_checked: bool = False
    http_checked: bool = False
    path_checked: bool = False
    knowledge_checked: bool = False

    def checked_names(self) -> list[str]:
        return [
            name
            for name, checked in self.model_dump().items()
            if checked
        ]


class EvidenceSufficiency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: DiagnosticGoal
    sufficient: bool
    reason: str = Field(min_length=1)
    required_coverage: list[str] = Field(default_factory=list)
    missing_coverage: list[str] = Field(default_factory=list)


class Observation(BaseModel):
    """Small common view over AgentToolStep and EvidenceRecord."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


_FULL_DIAGNOSIS_TERMS = (
    "完整诊断",
    "全面诊断",
    "全面检查",
    "逐步检查",
    "实际网络排障流程",
    "按照排障流程",
    "不要只给我一个可能原因",
    "不要只给一个可能原因",
)

_WEB_TERMS = (
    "网页",
    "网站",
    "浏览器",
    "http",
    "https",
    "页面一直转圈",
    "找不到服务器",
    "github.com",
)


def detect_diagnostic_goal(message: str, *, diagnostic: bool) -> DiagnosticGoal:
    if not diagnostic:
        return DiagnosticGoal.NON_DIAGNOSTIC
    text = message.casefold()
    web_related = any(term in text for term in _WEB_TERMS) or "打不开" in text
    if web_related and any(term in text for term in _FULL_DIAGNOSIS_TERMS):
        return DiagnosticGoal.FULL_WEB_DIAGNOSIS
    if web_related:
        return DiagnosticGoal.WEB_UNREACHABLE
    if "dns" in text or "域名解析" in text:
        return DiagnosticGoal.DNS_CHECK
    if any(term in text for term in ("tcp", "ssh", "端口")):
        return DiagnosticGoal.TCP_CHECK
    return DiagnosticGoal.GENERIC_DIAGNOSIS


def normalize_observations(
    *,
    steps: Sequence[Any] = (),
    evidence: Sequence[Any] = (),
) -> list[Observation]:
    observations: list[Observation] = []
    for record in evidence:
        if getattr(record, "reusable", True) is False:
            continue
        data = getattr(record, "data", {})
        observations.append(
            Observation(
                evidence_id=str(getattr(record, "evidence_id", "unknown")),
                tool_name=str(record.tool_name),
                arguments=dict(getattr(record, "arguments", {})),
                status=str(record.status),
                data=dict(data) if isinstance(data, dict) else {},
                summary=str(getattr(record, "summary", "")),
            )
        )
    for step in steps:
        raw_data = json_data(step.result.data)
        data = raw_data if isinstance(raw_data, dict) else {}
        error_code = None
        if step.result.error is not None:
            error_code = str(
                getattr(step.result.error.code, "value", step.result.error.code)
            )
        observations.append(
            Observation(
                evidence_id=f"tool_call:{step.tool_call_id}",
                tool_name=step.tool_name,
                arguments=dict(step.arguments),
                status=finding_status(
                    step.tool_name,
                    step.result.success,
                    data,
                    error_code,
                ),
                data=data,
                summary=step.result.summary,
            )
        )
    return observations


def coverage_from_observations(
    *,
    steps: Sequence[Any] = (),
    evidence: Sequence[Any] = (),
) -> DiagnosticCoverage:
    coverage = DiagnosticCoverage()
    for item in normalize_observations(steps=steps, evidence=evidence):
        if item.status in {"error", "blocked", "inconclusive", "unsupported", "unknown"}:
            continue
        if item.tool_name == "get_network_info":
            coverage.network_config_checked = True
        elif item.tool_name == "ping_host":
            if _looks_like_gateway(item.arguments.get("host")):
                coverage.gateway_checked = True
            else:
                coverage.ip_connectivity_checked = True
        elif item.tool_name == "dns_lookup":
            coverage.dns_checked = True
        elif item.tool_name == "tcp_check":
            coverage.tcp_checked = True
        elif item.tool_name == "http_check":
            coverage.http_checked = True
        elif item.tool_name == "traceroute":
            coverage.path_checked = True
        elif item.tool_name == "knowledge_search":
            coverage.knowledge_checked = True
    return coverage


def assess_evidence_sufficiency(
    message: str,
    coverage: DiagnosticCoverage,
    *,
    diagnostic: bool,
) -> EvidenceSufficiency:
    goal = detect_diagnostic_goal(message, diagnostic=diagnostic)
    required = _required_coverage(goal)
    missing = [name for name in required if not _coverage_value(coverage, name)]
    if goal is DiagnosticGoal.NON_DIAGNOSTIC:
        return EvidenceSufficiency(
            goal=goal,
            sufficient=True,
            reason="current turn does not require live diagnostic evidence",
        )
    if not missing:
        return EvidenceSufficiency(
            goal=goal,
            sufficient=True,
            reason="required evidence coverage for the user goal is present",
            required_coverage=required,
        )
    return EvidenceSufficiency(
        goal=goal,
        sufficient=False,
        reason="additional independent evidence is required before concluding",
        required_coverage=required,
        missing_coverage=missing,
    )


def _required_coverage(goal: DiagnosticGoal) -> list[str]:
    if goal is DiagnosticGoal.FULL_WEB_DIAGNOSIS:
        return ["network_config", "dns", "ip_connectivity", "application"]
    if goal is DiagnosticGoal.WEB_UNREACHABLE:
        return ["web_path"]
    if goal is DiagnosticGoal.DNS_CHECK:
        return ["dns"]
    if goal is DiagnosticGoal.TCP_CHECK:
        return ["tcp"]
    if goal is DiagnosticGoal.GENERIC_DIAGNOSIS:
        return ["any_network"]
    return []


def _coverage_value(coverage: DiagnosticCoverage, name: str) -> bool:
    if name == "network_config":
        return coverage.network_config_checked
    if name == "dns":
        return coverage.dns_checked
    if name == "ip_connectivity":
        return coverage.ip_connectivity_checked
    if name == "tcp":
        return coverage.tcp_checked
    if name == "application":
        return coverage.tcp_checked or coverage.http_checked
    if name == "web_path":
        return coverage.dns_checked or coverage.tcp_checked or coverage.http_checked
    if name == "any_network":
        values: Iterable[bool] = coverage.model_dump(exclude={"knowledge_checked"}).values()
        return any(values)
    return False


def _looks_like_gateway(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_private or address.is_link_local
