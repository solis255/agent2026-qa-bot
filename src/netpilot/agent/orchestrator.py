"""Bounded native Function Calling loop for NetPilot diagnoses."""

from __future__ import annotations

import json
from collections.abc import Sequence

from netpilot.agent.evidence import finding_status, json_data, llm_tool_feedback
from netpilot.agent.prompts import NETPILOT_SYSTEM_PROMPT
from netpilot.agent.schemas import AgentResult, AgentStatus, AgentToolStep
from netpilot.agent.tool_registry import ToolRegistry
from netpilot.llm import (
    ChatMessage,
    ChatRole,
    LLMClient,
    TJUClientError,
    TokenUsage,
)
from netpilot.rag import KnowledgeSearchData, KnowledgeSource


MAX_TOOL_ROUNDS_ANSWER = "已达到自动诊断步骤上限，当前证据不足以继续自动分析。"


class AgentOrchestrator:
    """Coordinate the model and allowlisted tools without arbitrary execution."""

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        *,
        max_tool_rounds: int = 6,
        system_prompt: str = NETPILOT_SYSTEM_PROMPT,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be at least 1")
        self.llm = llm
        self.registry = registry
        self.max_tool_rounds = max_tool_rounds
        self.system_prompt = system_prompt.strip()

    def run(
        self,
        user_message: str,
        *,
        history: Sequence[ChatMessage] = (),
    ) -> AgentResult:
        """Run one bounded diagnosis with optional pre-trimmed text history."""

        if any(
            message.role not in {ChatRole.USER, ChatRole.ASSISTANT}
            or message.tool_calls
            or message.tool_call_id is not None
            for message in history
        ):
            raise ValueError("history must contain text-only user and assistant messages")

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=self.system_prompt),
            *[message.model_copy(deep=True) for message in history],
            ChatMessage(role=ChatRole.USER, content=user_message),
        ]
        steps: list[AgentToolStep] = []
        usage = TokenUsage()
        llm_duration_ms = 0.0
        tool_rounds = 0
        sources: list[KnowledgeSource] = []
        tools = self.registry.schemas()
        tool_schemas = {
            schema["function"]["name"]: schema
            for schema in tools
        }
        requested_tools = {
            name for name in tool_schemas if name.lower() in user_message.lower()
        }
        completed_requested_tools: set[str] = set()
        executed_calls: set[tuple[str, str]] = set()
        next_tools = tools
        next_tool_choice = "auto"
        missing_tool_attempts = 0

        while True:
            final_answer_requested = next_tool_choice == "none"
            try:
                response = self.llm.chat(
                    messages,
                    tools=next_tools,
                    tool_choice=next_tool_choice,
                    temperature=0.2,
                    max_tokens=1200,
                )
            except TJUClientError as exc:
                missing_requested = requested_tools - completed_requested_tools
                if steps:
                    if missing_requested and missing_tool_attempts < 2:
                        missing_tool_attempts += 1
                        continue
                    return _fallback_result(
                        steps,
                        sources,
                        usage,
                        llm_duration_ms,
                        tool_rounds,
                    )
                return AgentResult(
                    answer=str(exc),
                    status=AgentStatus.LLM_ERROR,
                    tool_rounds=tool_rounds,
                    steps=steps,
                    sources=sources,
                    usage=usage,
                    llm_duration_ms=llm_duration_ms,
                )
            next_tools = tools
            next_tool_choice = "auto"

            usage = usage.add(response.usage)
            llm_duration_ms += response.duration_ms
            messages.append(response.to_assistant_message())

            if not response.tool_calls:
                assert response.content is not None
                missing_requested = requested_tools - completed_requested_tools
                if missing_requested and missing_tool_attempts < 2:
                    next_tools = [
                        tool_schemas[name]
                        for name in sorted(missing_requested)
                    ]
                    next_tool_choice = "auto"
                    missing_tool_attempts += 1
                    messages.append(_missing_tools_message(missing_requested))
                    continue
                if missing_requested:
                    return _fallback_result(
                        steps,
                        sources,
                        usage,
                        llm_duration_ms,
                        tool_rounds,
                    )
                if final_answer_requested and _looks_like_textual_tool_call(
                    response.content
                ):
                    return _fallback_result(
                        steps,
                        sources,
                        usage,
                        llm_duration_ms,
                        tool_rounds,
                    )
                return AgentResult(
                    answer=response.content,
                    status=AgentStatus.COMPLETED,
                    tool_rounds=tool_rounds,
                    steps=steps,
                    sources=sources,
                    usage=usage,
                    llm_duration_ms=llm_duration_ms,
                )

            if final_answer_requested:
                return _fallback_result(
                    steps,
                    sources,
                    usage,
                    llm_duration_ms,
                    tool_rounds,
                )

            if tool_rounds >= self.max_tool_rounds:
                if steps:
                    return _fallback_result(
                        steps,
                        sources,
                        usage,
                        llm_duration_ms,
                        tool_rounds,
                        status=AgentStatus.MAX_TOOL_ROUNDS,
                    )
                return AgentResult(
                    answer=MAX_TOOL_ROUNDS_ANSWER,
                    status=AgentStatus.MAX_TOOL_ROUNDS,
                    tool_rounds=tool_rounds,
                    steps=steps,
                    sources=sources,
                    usage=usage,
                    llm_duration_ms=llm_duration_ms,
                )

            tool_rounds += 1
            duplicate_count = 0
            for tool_call in response.tool_calls:
                signature = _call_signature(
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
                if signature in executed_calls:
                    duplicate_count += 1
                    messages.append(
                        ChatMessage(
                            role=ChatRole.TOOL,
                            tool_call_id=tool_call.id,
                            content=json.dumps(
                                {
                                    "execution_status": "success",
                                    "finding_status": "already_observed",
                                    "summary": (
                                        "相同工具和参数已经执行；请使用已有证据，"
                                        "停止重复检测并给出最终回答。"
                                    ),
                                    "evidence": None,
                                    "error": None,
                                },
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        )
                    )
                    continue
                executed_calls.add(signature)
                execution = self.registry.execute(
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
                steps.append(
                    AgentToolStep(
                        round=tool_rounds,
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.function.name,
                        arguments=execution.arguments,
                        result=execution.result,
                    )
                )
                if tool_call.function.name == "knowledge_search":
                    sources = _merge_sources(sources, execution.result.data)
                if execution.result.success:
                    completed_requested_tools.add(tool_call.function.name)
                messages.append(
                    ChatMessage(
                        role=ChatRole.TOOL,
                        tool_call_id=tool_call.id,
                        content=json.dumps(
                            llm_tool_feedback(tool_call.function.name, execution.result),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                )
            missing_requested = requested_tools - completed_requested_tools
            if missing_requested:
                if missing_tool_attempts >= 2:
                    return _fallback_result(
                        steps,
                        sources,
                        usage,
                        llm_duration_ms,
                        tool_rounds,
                    )
                next_tools = [
                    tool_schemas[name]
                    for name in sorted(missing_requested)
                ]
                next_tool_choice = "auto"
                missing_tool_attempts += 1
                messages.append(_missing_tools_message(missing_requested))
            elif requested_tools or _has_decisive_abnormal_evidence(steps):
                next_tool_choice = "none"
            elif duplicate_count == len(response.tool_calls):
                return _fallback_result(
                    steps,
                    sources,
                    usage,
                    llm_duration_ms,
                    tool_rounds,
                )


def _call_signature(tool_name: str, raw_arguments: str) -> tuple[str, str]:
    """Canonicalize a diagnostic target so tuning changes cannot bypass dedup."""

    try:
        arguments = json.loads(raw_arguments)
        signature_fields = {
            "ping_host": ("host",),
            "dns_lookup": ("domain",),
            "tcp_check": ("host", "port"),
            "http_check": ("url",),
            "traceroute": ("host",),
            "knowledge_search": ("query",),
        }.get(tool_name)
        if isinstance(arguments, dict) and signature_fields is not None:
            arguments = {
                field: _normalize_signature_value(arguments.get(field))
                for field in signature_fields
            }
        canonical = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        canonical = str(raw_arguments).strip()
    return tool_name, canonical


def _normalize_signature_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    return value.strip().lower().rstrip(".")


def _missing_tools_message(missing_tools: set[str]) -> ChatMessage:
    names = "、".join(sorted(missing_tools))
    return ChatMessage(
        role=ChatRole.SYSTEM,
        content=(
            f"用户明确要求的检测尚未完成：{names}。"
            "下一轮只能调用提供的剩余工具；在拿到结果前不得输出最终结论，"
            "也不得重复已经完成的工具。"
        ),
    )


def _looks_like_textual_tool_call(content: str) -> bool:
    lowered = content.lower()
    return "<tool_call" in lowered or "<function=" in lowered


def _fallback_result(
    steps: list[AgentToolStep],
    sources: list[KnowledgeSource],
    usage: TokenUsage,
    llm_duration_ms: float,
    tool_rounds: int,
    *,
    status: AgentStatus = AgentStatus.COMPLETED,
) -> AgentResult:
    return AgentResult(
        answer=_evidence_fallback_answer(steps),
        status=status,
        tool_rounds=tool_rounds,
        steps=steps,
        sources=sources,
        usage=usage,
        llm_duration_ms=llm_duration_ms,
    )


def _has_decisive_abnormal_evidence(steps: list[AgentToolStep]) -> bool:
    """Stop exploratory calls once a network tool has found a concrete issue."""

    return any(
        step.tool_name != "knowledge_search"
        and finding_status(
            step.tool_name,
            step.result.success,
            json_data(step.result.data),
        )
        == "abnormal"
        for step in steps
    )


def _evidence_fallback_answer(steps: list[AgentToolStep]) -> str:
    """Produce a stable conclusion when a model loops on an existing check."""

    lines: list[str] = []
    statuses: list[str] = []
    abnormal_tools: set[str] = set()
    has_error = False
    labels = {
        "get_network_info": "网络接口",
        "ping_host": "Ping 可达性",
        "dns_lookup": "DNS 解析",
        "tcp_check": "TCP 端口",
        "http_check": "HTTP 访问",
        "traceroute": "路由追踪",
        "knowledge_search": "校园网络知识检索",
    }
    for step in steps:
        status = finding_status(
            step.tool_name,
            step.result.success,
            json_data(step.result.data),
        )
        statuses.append(status)
        if status == "abnormal":
            abnormal_tools.add(step.tool_name)
        elif status == "error":
            has_error = True
        marker = {
            "normal": "正常",
            "abnormal": "发现异常",
            "error": "执行失败",
            "reference": "已找到参考资料",
        }[status]
        label = labels.get(step.tool_name, step.tool_name)
        lines.append(f"- {label}：{marker}，{step.result.summary}")

    if "abnormal" in statuses:
        judgment = "现有证据显示网络检查存在异常。"
    elif has_error:
        judgment = "部分检测未能执行，现有证据不足以排除网络问题。"
    else:
        judgment = "现有检测未发现明显网络异常。"

    suggestions: list[str] = []
    if "dns_lookup" in abnormal_tools:
        suggestions.append("检查设备当前 DNS 配置，断开并重新连接网络后再试。")
    if {"ping_host", "get_network_info", "traceroute"} & abnormal_tools:
        suggestions.append("检查 Wi-Fi 或网线连接，并确认是否能访问默认网关。")
    if {"tcp_check", "http_check"} & abnormal_tools:
        suggestions.append("确认目标服务地址、端口和服务状态后重试。")
    if has_error:
        suggestions.append("可稍后重试失败的检测，避免把工具失败当作网络故障。")
    if not suggestions:
        suggestions.append("若现象仍存在，请补充目标地址、错误提示和发生范围后继续诊断。")

    return (
        f"问题判断：{judgment}\n\n"
        "检测结果：\n"
        + "\n".join(lines)
        + "\n\n建议操作：\n"
        + "\n".join(f"- {suggestion}" for suggestion in suggestions)
    )


def _merge_sources(
    existing: list[KnowledgeSource],
    data: object,
) -> list[KnowledgeSource]:
    if isinstance(data, KnowledgeSearchData):
        results = data.results
    elif isinstance(data, dict):
        try:
            results = KnowledgeSearchData.model_validate(data).results
        except ValueError:
            return existing
    else:
        return existing
    merged = list(existing)
    known = {source.chunk_id for source in merged}
    for result in results:
        if result.chunk_id in known:
            continue
        merged.append(
            KnowledgeSource(
                title=result.title,
                source=result.source,
                source_type=result.source_type,
                file=result.file,
                chunk_id=result.chunk_id,
                score=result.score,
            )
        )
        known.add(result.chunk_id)
    return merged
