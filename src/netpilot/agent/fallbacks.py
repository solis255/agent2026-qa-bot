"""Intent-aware deterministic responses for failed model finalization."""

from __future__ import annotations

from collections.abc import Iterable

from netpilot.agent.diagnosis import build_diagnostic_answer, step_status
from netpilot.agent.hypotheses import Hypothesis
from netpilot.agent.intent import TurnIntent
from netpilot.agent.response_modes import ResponseMode
from netpilot.agent.schemas import AgentToolStep, FallbackReason
from netpilot.agent.task_state import EvidenceRecord
from netpilot.rag import KnowledgeSource


def build_intent_fallback(
    *,
    intent: TurnIntent | None,
    response_mode: ResponseMode | None,
    reason: FallbackReason,
    user_message: str,
    steps: list[AgentToolStep],
    evidence: list[EvidenceRecord],
    sources: list[KnowledgeSource],
    hypotheses: list[Hypothesis],
) -> str:
    """Generate a safe response that preserves the current Turn's purpose."""

    del reason  # Exposed as metadata; do not clutter the user-facing answer.
    if intent is TurnIntent.REPORT_REQUEST or response_mode is ResponseMode.REPORT:
        return _report_fallback(user_message, steps, evidence, sources, hypotheses)
    if intent is TurnIntent.META_FEEDBACK or response_mode is ResponseMode.META:
        return _meta_fallback(user_message, evidence)
    if intent in {
        TurnIntent.ANALYZE_EXISTING,
        TurnIntent.COMPARE,
        TurnIntent.FOLLOWUP_ACTION,
    } or response_mode in {ResponseMode.ANALYSIS, ResponseMode.COMPARISON}:
        return _analysis_fallback(evidence, steps, sources, hypotheses)
    if response_mode is ResponseMode.KNOWLEDGE:
        return _knowledge_fallback(sources)
    if steps:
        network_steps = [step for step in steps if step.tool_name != "knowledge_search"]
        if network_steps:
            return build_diagnostic_answer(network_steps, hypotheses=hypotheses)
    if evidence:
        return _analysis_fallback(evidence, steps, sources, hypotheses)
    return "本轮无法取得足够依据完成回答，请稍后重试或补充更具体的问题。"


def _report_fallback(
    user_message: str,
    steps: list[AgentToolStep],
    evidence: list[EvidenceRecord],
    sources: list[KnowledgeSource],
    hypotheses: list[Hypothesis],
) -> str:
    network = _network_lines(evidence, steps)
    abnormal = [line for status, line in network if status != "normal"]
    normal = [line for status, line in network if status == "normal"]
    tools = _unique(
        [record.tool_name for record in evidence if record.tool_name != "knowledge_search"]
        + [step.tool_name for step in steps if step.tool_name != "knowledge_search"]
    )
    supported = [item.name for item in hypotheses if item.status == "supported"]
    possible = [item.name for item in hypotheses if item.status == "possible"]
    conclusion = (
        "已支持的故障假设：" + "、".join(supported)
        if supported
        else "现有证据尚不足以确认单一根因。"
    )
    if possible:
        conclusion += " 待验证：" + "、".join(possible) + "。"
    source_lines = [_source_line(item) for item in sources]
    evidence_lines = abnormal or ["暂无异常 Network Evidence。"]
    if source_lines:
        evidence_lines += ["知识库 Source（仅作操作参考）：", *source_lines]
    return "\n\n".join(
        [
            "现象\n" + user_message.strip(),
            "检测步骤\n" + _bullets(tools or ["本轮未执行新的网络检测。"]),
            "证据\n" + _bullets(evidence_lines),
            "排除项\n" + _bullets(normal or ["暂无足够正常证据形成排除项。"]),
            "初步结论\n" + conclusion,
            "建议\n"
            + _bullets(
                [
                    "优先处理已获支持且影响范围最大的假设。",
                    "未覆盖的网络层级应只补充最少必要检测，不重复已有 Tool。",
                    "知识库 Source 仅用于操作参考，不能替代实时 Network Evidence。",
                ]
            ),
        ]
    )


def _meta_fallback(user_message: str, evidence: list[EvidenceRecord]) -> str:
    network_count = sum(
        record.tool_name != "knowledge_search" for record in evidence
    )
    return (
        f"收到你的反馈：“{user_message.strip()}”。刚才的回答没有充分贴合你的要求。"
        "我不会因此重新运行网络检测或重复固定故障模板。"
        f"当前会话已有 {network_count} 条实时 Network Evidence；后续回答会聚合已有结果，"
        "明确区分已确认、未确认和知识库参考。如果你指出具体遗漏，我会直接针对该点修正。"
    )


def _analysis_fallback(
    evidence: list[EvidenceRecord],
    steps: list[AgentToolStep],
    sources: list[KnowledgeSource],
    hypotheses: list[Hypothesis],
) -> str:
    network = _network_lines(evidence, steps)
    abnormal = [line for status, line in network if status != "normal"]
    normal = [line for status, line in network if status == "normal"]
    unresolved = [
        f"{item.name}：{item.status}"
        for item in hypotheses
        if item.status in {"possible", "supported"}
    ]
    return "\n\n".join(
        [
            "已有 Network Evidence 分析\n"
            + _bullets(abnormal or ["暂无异常实时证据。"]),
            "正常与排除证据\n" + _bullets(normal or ["暂无。"]),
            "未解决假设\n" + _bullets(unresolved or ["暂无结构化未解决假设。"]),
            "Knowledge Sources（操作参考，不是实时证据）\n"
            + _bullets(
                [_source_line(item) for item in sources]
                or ["本次没有可用知识库来源。"]
            ),
            "结论限制\n现有内容只支持上述观察；缺失的层级仍需补证，不能据此扩大结论。",
        ]
    )


def _knowledge_fallback(sources: list[KnowledgeSource]) -> str:
    if not sources:
        return "知识库没有提供足够来源完成回答；本轮没有把实时网络状态当作知识依据。"
    return (
        "已找到以下知识库 Source，但模型未能完成最终整理。它们仅作操作参考：\n"
        + _bullets([_source_line(item) for item in sources])
    )


def _network_lines(
    evidence: Iterable[EvidenceRecord],
    steps: Iterable[AgentToolStep],
) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in evidence:
        if record.tool_name == "knowledge_search":
            continue
        line = f"{record.tool_name}：{record.summary}"
        if line not in seen:
            seen.add(line)
            lines.append((record.status, line))
    for step in steps:
        if step.tool_name == "knowledge_search":
            continue
        line = f"{step.tool_name}：{step.result.summary}"
        if line not in seen:
            seen.add(line)
            lines.append((step_status(step), line))
    return lines


def _source_line(source: KnowledgeSource) -> str:
    return f"[{source.source_type.value}] {source.title} — {source.source}"


def _bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _unique(items: Iterable[str]) -> list[str]:
    output: list[str] = []
    for item in items:
        if item not in output:
            output.append(item)
    return output
