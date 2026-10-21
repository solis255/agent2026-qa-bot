"""Deterministic routing over existing context, target and evidence policies."""
from __future__ import annotations

import re

from .models import DiagnosticReadiness

# Snapshot v1 has no public-IP ping, HTTP or traceroute observation. The
# composite coverage names are the existing Sufficiency vocabulary.
WINDOWS_COLLECTOR_COVERAGE = frozenset({
    "network_config", "gateway", "dns", "tcp", "application", "web_path", "any_network",
})
DIAGNOSTIC_INTENTS = frozenset({"diagnose", "clarify", "state_changed", "analyze_existing", "compare", "followup_action"})


def client_evidence_support(environment) -> bool | None:
    if environment.os_family == "unknown":
        return None
    return environment.os_family == "windows"


def explicit_client_check(message):
    text = message.casefold()
    if re.search(r"如果|假设|例如|不要|无需|不必", text):
        return False
    return bool(re.search(r"(?:检查|检测|诊断|看看|查看).{0,16}(?:dns|域名解析|默认网关|我的网络|我的电脑|网络状态)|(?:dns_lookup|ping_host|tcp_check|http_check|traceroute|get_network_info)", text))


def assess_diagnostic_readiness(*, classification, message, environment,
    context_question, target, provider_kind, reusable_evidence=(), coverage=None,
    evidence_sufficiency=None, task_version=1, acquisition_state=None, previous_readiness=None):
    # Runtime imports keep conversation_context independently importable.
    from netpilot.agent.coverage import coverage_from_observations, assess_evidence_sufficiency
    from netpilot.agent.target_capabilities import evaluate_target_capabilities
    from netpilot.client_snapshot.service import usable_client_snapshot_records

    records = list(reusable_evidence)
    usable = usable_client_snapshot_records(records, task_version=task_version, target=target)
    records = [r for r in records if r.evidence_origin != "client_snapshot" or r in usable]
    capability = evaluate_target_capabilities(target, provider_kind, has_client_snapshot_evidence=bool(usable))
    kind = getattr(classification.intent, "value", classification.intent)
    continuing = bool(previous_readiness and previous_readiness.state == "need_client_evidence"
        and (previous_readiness.task_version, previous_readiness.target_version) == (task_version, target.target_version)
        and re.fullmatch(r"(?:那怎么办|下一步呢|那下一步呢|怎么办)[？?。!！]?", message.strip()))
    if continuing:
        kind = "followup_action"
    explicit = explicit_client_check(message)
    radio = bool(re.search(r"(?:看不到|找不到|搜不到).{0,10}(?:wifi|wi-fi|无线)|(?:wifi|wi-fi|无线).{0,10}(?:看不到|找不到|搜不到)", message, re.I))
    diagnostic = kind in DIAGNOSTIC_INTENTS or explicit or radio
    coverage = coverage if coverage is not None else coverage_from_observations(evidence=records)
    sufficiency = evidence_sufficiency if evidence_sufficiency is not None else assess_evidence_sufficiency(message, coverage, diagnostic=diagnostic)
    base = dict(target_subject=target.subject, target_version=target.target_version, task_version=task_version,
        can_use_host_network_tools=capability.can_use_host_network_tools,
        can_use_mock_tools=capability.can_use_mock_tools,
        has_usable_client_evidence=bool(usable), client_evidence_supported=client_evidence_support(environment))

    def decision(state, action, reason, **values):
        return DiagnosticReadiness(state=state, recommended_action=action, reason=reason, **base, **values)

    if context_question is not None:
        return decision("need_context", "ask_context", "necessary_context_missing", missing_context_fields=[context_question.field])
    if kind in {"knowledge_request", "general_question"} and not explicit and not radio:
        return decision("knowledge_only", "answer_knowledge", "knowledge_without_live_evidence")
    if not diagnostic:
        return decision("ready", "continue_with_limitations", "non_diagnostic_turn")
    if sufficiency.sufficient:
        return decision("ready", "analyze_existing", "current_evidence_sufficient")
    if capability.can_use_host_network_tools or capability.can_use_mock_tools:
        return decision("ready", "run_allowed_diagnostics", "target_tools_available", evidence_gap=sufficiency.missing_coverage)
    if target.subject != "user_client" or target.relationship_to_netpilot != "remote":
        return decision("ready", "continue_with_limitations", "target_not_directly_observable", evidence_gap=sufficiency.missing_coverage)
    # Radio visibility is not a DNS/TCP measurement problem.
    requires_client = continuing or explicit or (environment.affected_scope in {"web_only", "all_network"} and not radio)
    if not requires_client:
        return decision("ready", "continue_with_limitations", "symptom_guidance_before_collection")
    gaps = sufficiency.missing_coverage
    if usable and any(gap not in WINDOWS_COLLECTOR_COVERAGE for gap in gaps):
        return decision("ready", "continue_with_limitations", "collector_cannot_fill_remaining_gap", evidence_gap=gaps)
    if base["client_evidence_supported"] is None:
        state = acquisition_state
        if state is None or ("os_family" not in state.asked_fields and "os_family" not in state.unknown_fields):
            return decision("need_context", "ask_context", "collector_platform_unknown", missing_context_fields=["os_family"], evidence_gap=gaps)
        return decision("ready", "continue_with_limitations", "platform_answer_unavailable", evidence_gap=gaps)
    return decision("need_client_evidence", "request_client_evidence" if base["client_evidence_supported"] else "continue_with_limitations",
                    "current_client_evidence_missing" if not usable else "client_coverage_incomplete", evidence_gap=gaps)


def readiness_answer(readiness, *, previous=None, message=""):
    """Temporary 13B explanation; no ClientCheckAction or collector commands."""
    repeated = previous and (previous.task_version, previous.target_version, previous.state) == (readiness.task_version, readiness.target_version, "need_client_evidence")
    if repeated and re.fullmatch(r"(?:那怎么办|下一步呢|那下一步呢|怎么办)[？?。!！]?", message.strip()):
        return "如果暂时不提供客户端证据，可以先确认接入/认证状态、比较其他应用与网站，再核对 VPN 或代理开关；结论仍保持为“证据不足”。"
    if readiness.client_evidence_supported:
        return ("当前诊断对象是你的远程设备。要继续判断 DNS、默认网关或基础连通状态，需要客户端侧证据；NetPilot 服务主机的检测结果不能代替你的电脑。\n\n"
                "现阶段可使用已有的客户端诊断快照功能采集并上传当前设备状态。旧快照仅代表历史采集状态，不能证明当前网络状态。尚不能确认网络根因。")
    return ("当前还缺少这台设备的直接网络证据。现阶段客户端诊断快照仅支持 Windows；接下来只能基于你提供的现象和知识给出受限排查建议。\n\n"
            "可以先确认接入/认证状态、比较其他应用和网站，并核对 VPN 或代理是否开启。环境声明不是检测证据，尚不能确认 DNS、默认网关或网络根因。")


def trace_readiness(trace, readiness):
    labels = {"knowledge_only":"直接知识回答", "need_context":"补充必要环境", "need_client_evidence":"需要客户端证据", "ready":"可以继续"}
    if readiness.recommended_action == "analyze_existing":
        label = "复用已有证据"
    else:
        label = labels[readiness.state]
    trace.append("decision", "诊断准备度：" + label,
        f"对象 {readiness.target_subject} v{readiness.target_version}，任务 v{readiness.task_version}；"
        f"{readiness.reason}；下一步 {readiness.recommended_action}。环境信息不是检测证据，准备度不授予工具权限。")
