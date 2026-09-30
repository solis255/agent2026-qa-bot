"""Bounded native Function Calling loop for NetPilot diagnoses."""

from __future__ import annotations

import json
from collections.abc import Sequence

from netpilot.agent.coverage import (
    DiagnosticCoverage,
    DiagnosticGoal,
    EvidenceSufficiency,
    assess_evidence_sufficiency,
    coverage_from_observations,
)
from netpilot.agent.context_builder import build_task_context_message
from netpilot.agent.evidence import llm_tool_feedback, model_safe_data
from netpilot.agent.fallbacks import build_intent_fallback
from netpilot.agent.hypotheses import Hypothesis, track_hypotheses
from netpilot.agent.intent import TurnIntent, classify_turn_intent
from netpilot.agent.prompts import NETPILOT_SYSTEM_PROMPT
from netpilot.agent.response_modes import (
    ResponseMode,
    clarification_answer,
    response_mode_for,
    response_mode_message,
)
from netpilot.agent.rag_policy import find_duplicate_rag_query
from netpilot.agent.schemas import (
    AgentResult,
    AgentStatus,
    AgentToolStep,
    FallbackReason,
)
from netpilot.agent.task_state import EvidenceRecord, SessionTaskState
from netpilot.agent.tool_policy import build_tool_policy
from netpilot.agent.tool_registry import ToolRegistry
from netpilot.agent.tool_signature import canonical_tool_signature
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
        max_rag_calls_per_turn: int = 2,
        max_output_tokens: int = 1600,
        report_max_output_tokens: int = 2800,
        system_prompt: str = NETPILOT_SYSTEM_PROMPT,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be at least 1")
        if max_rag_calls_per_turn < 1:
            raise ValueError("max_rag_calls_per_turn must be at least 1")
        if not 1 <= max_output_tokens <= 32_768:
            raise ValueError("max_output_tokens must be between 1 and 32768")
        if not 1 <= report_max_output_tokens <= 32_768:
            raise ValueError("report_max_output_tokens must be between 1 and 32768")
        self.llm = llm
        self.registry = registry
        self.max_tool_rounds = max_tool_rounds
        self.max_rag_calls_per_turn = max_rag_calls_per_turn
        self.max_output_tokens = max_output_tokens
        self.report_max_output_tokens = report_max_output_tokens
        self.system_prompt = system_prompt.strip()

    def run(
        self,
        user_message: str,
        *,
        history: Sequence[ChatMessage] = (),
        task_state: SessionTaskState | None = None,
    ) -> AgentResult:
        """Run one bounded diagnosis with text history and structured evidence."""

        if any(
            message.role not in {ChatRole.USER, ChatRole.ASSISTANT}
            or message.tool_calls
            or message.tool_call_id is not None
            for message in history
        ):
            raise ValueError("history must contain text-only user and assistant messages")

        effective_task_state = (
            task_state.model_copy(deep=True) if task_state is not None else None
        )
        classification = classify_turn_intent(
            user_message,
            has_evidence=bool(
                effective_task_state and effective_task_state.reusable_evidence()
            ),
        )
        task_version_advanced = classification.intent is TurnIntent.STATE_CHANGED
        if task_version_advanced and effective_task_state is not None:
            effective_task_state.advance_version()
        response_mode = response_mode_for(classification.intent)
        existing_records = (
            effective_task_state.reusable_evidence()
            if effective_task_state is not None
            else []
        )
        existing_evidence = {
            record.tool_signature: record for record in existing_records
        }
        policy = build_tool_policy(
            classification,
            blocked_signatures=set(existing_evidence),
        )
        steps: list[AgentToolStep] = []
        diagnostic_turn = classification.intent in {
            TurnIntent.DIAGNOSE,
            TurnIntent.STATE_CHANGED,
        }
        coverage = coverage_from_observations(
            evidence=existing_records,
        )
        sufficiency = assess_evidence_sufficiency(
            user_message,
            coverage,
            diagnostic=diagnostic_turn,
        )
        hypotheses = track_hypotheses(evidence=existing_records)
        result_metadata = {
            "turn_intent": classification.intent,
            "response_mode": response_mode,
            "task_version_advanced": task_version_advanced,
            "coverage": coverage,
            "evidence_sufficiency": sufficiency,
            "hypotheses": hypotheses,
        }
        if classification.intent is TurnIntent.CLARIFY:
            return AgentResult(
                answer=clarification_answer(),
                status=AgentStatus.COMPLETED,
                tool_rounds=0,
                **result_metadata,
            )

        sources = _sources_from_evidence(existing_records)
        messages = [ChatMessage(role=ChatRole.SYSTEM, content=self.system_prompt)]
        messages.append(response_mode_message(response_mode))
        messages.append(
            build_task_context_message(
                user_message=user_message,
                intent=classification.intent,
                task_version=(
                    effective_task_state.task_version
                    if effective_task_state is not None
                    else 1
                ),
                evidence=existing_records,
                coverage=coverage,
                sufficiency=sufficiency,
                hypotheses=hypotheses,
                sources=sources,
            )
        )
        messages.extend(message.model_copy(deep=True) for message in history)
        messages.append(ChatMessage(role=ChatRole.USER, content=user_message))
        usage = TokenUsage()
        llm_duration_ms = 0.0
        tool_rounds = 0
        tools = policy.filter_schemas(self.registry.schemas())
        tool_schemas = {
            schema["function"]["name"]: schema
            for schema in tools
        }
        requested_tools = {
            name for name in tool_schemas if name.lower() in user_message.lower()
        }
        completed_requested_tools: set[str] = set()
        executed_calls: set[str] = set(policy.blocked_signatures)
        reused_evidence_ids: list[str] = []
        next_tools = tools or None
        next_tool_choice = "auto" if tools else "none"
        missing_tool_attempts = 0
        coverage_prompt_attempts = 0
        rag_calls = 0
        rag_queries = [
            str(record.arguments.get("query", ""))
            for record in existing_records
            if record.tool_name == "knowledge_search"
            and record.arguments.get("query")
        ]
        rag_records = [
            record
            for record in existing_records
            if record.tool_name == "knowledge_search"
            and record.arguments.get("query")
        ]

        def fallback(
            reason: FallbackReason,
            *,
            status: AgentStatus = AgentStatus.COMPLETED,
        ) -> AgentResult:
            return _fallback_result(
                steps,
                sources,
                usage,
                llm_duration_ms,
                tool_rounds,
                reason=reason,
                user_message=user_message,
                evidence=existing_records,
                status=status,
                reused_evidence_ids=reused_evidence_ids,
                **result_metadata,
            )

        def current_context_message() -> ChatMessage:
            return build_task_context_message(
                user_message=user_message,
                intent=classification.intent,
                task_version=(
                    effective_task_state.task_version
                    if effective_task_state is not None
                    else 1
                ),
                evidence=existing_records,
                steps=steps,
                coverage=coverage,
                sufficiency=sufficiency,
                hypotheses=hypotheses,
                sources=sources,
            )

        while True:
            final_answer_requested = next_tool_choice == "none"
            try:
                response = self.llm.chat(
                    messages,
                    tools=next_tools,
                    tool_choice=next_tool_choice,
                    temperature=0.2,
                    max_tokens=(
                        self.report_max_output_tokens
                        if response_mode is ResponseMode.REPORT
                        else self.max_output_tokens
                    ),
                )
            except TJUClientError as exc:
                missing_requested = requested_tools - completed_requested_tools
                if steps or existing_records or response_mode in {
                    ResponseMode.REPORT,
                    ResponseMode.META,
                    ResponseMode.ANALYSIS,
                    ResponseMode.COMPARISON,
                }:
                    if missing_requested and missing_tool_attempts < 2:
                        missing_tool_attempts += 1
                        continue
                    return fallback(FallbackReason.LLM_ERROR)
                return AgentResult(
                    answer=str(exc),
                    status=AgentStatus.LLM_ERROR,
                    tool_rounds=tool_rounds,
                    steps=steps,
                    sources=sources,
                    usage=usage,
                    llm_duration_ms=llm_duration_ms,
                    reused_evidence_ids=reused_evidence_ids,
                    **result_metadata,
                )
            next_tools = tools or None
            next_tool_choice = "auto" if tools else "none"

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
                sufficiency = result_metadata["evidence_sufficiency"]
                only_failed_attempts = bool(steps) and not any(
                    step.result.success for step in steps
                )
                if (
                    diagnostic_turn
                    and isinstance(sufficiency, EvidenceSufficiency)
                    and not sufficiency.sufficient
                    and not only_failed_attempts
                    and coverage_prompt_attempts < 2
                ):
                    coverage_prompt_attempts += 1
                    next_tools = tools or None
                    next_tool_choice = "auto"
                    messages.append(
                        _coverage_gap_message(
                            sufficiency,
                            hypotheses,
                        )
                    )
                    continue
                if missing_requested:
                    return fallback(FallbackReason.FINALIZATION_FAILED)
                if final_answer_requested and _looks_like_textual_tool_call(
                    response.content
                ):
                    return fallback(FallbackReason.FINALIZATION_FAILED)
                return AgentResult(
                    answer=_deduplicate_consecutive_lines(response.content),
                    status=AgentStatus.COMPLETED,
                    tool_rounds=tool_rounds,
                    steps=steps,
                    sources=sources,
                    usage=usage,
                    llm_duration_ms=llm_duration_ms,
                    reused_evidence_ids=reused_evidence_ids,
                    **result_metadata,
                )

            if final_answer_requested:
                return fallback(FallbackReason.INVALID_TOOL_LOOP)

            if tool_rounds >= self.max_tool_rounds:
                if steps:
                    return fallback(
                        FallbackReason.MAX_TOOL_ROUNDS,
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
                    reused_evidence_ids=reused_evidence_ids,
                    fallback_reason=FallbackReason.MAX_TOOL_ROUNDS,
                    **result_metadata,
                )

            tool_rounds += 1
            duplicate_count = 0
            for tool_call in response.tool_calls:
                normalized_arguments = self.registry.normalize_arguments(
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
                signature = (
                    canonical_tool_signature(
                        tool_call.function.name,
                        normalized_arguments,
                    )
                    if normalized_arguments is not None
                    else None
                )
                rag_query: str | None = None
                if (
                    tool_call.function.name == "knowledge_search"
                    and normalized_arguments is not None
                ):
                    candidate = normalized_arguments.get("query")
                    rag_query = candidate if isinstance(candidate, str) else None
                    if rag_query is not None:
                        duplicate_query = find_duplicate_rag_query(
                            rag_query,
                            rag_queries,
                        )
                        if duplicate_query is not None:
                            duplicate_count += 1
                            previous = next(
                                (
                                    record
                                    for record in rag_records
                                    if find_duplicate_rag_query(
                                        rag_query,
                                        [str(record.arguments.get("query", ""))],
                                    )
                                    is not None
                                ),
                                None,
                            )
                            if previous is not None:
                                if previous.evidence_id not in reused_evidence_ids:
                                    reused_evidence_ids.append(previous.evidence_id)
                                sources = _merge_sources(sources, previous.data)
                            completed_requested_tools.add("knowledge_search")
                            messages.append(
                                ChatMessage(
                                    role=ChatRole.TOOL,
                                    tool_call_id=tool_call.id,
                                    content=_rag_reuse_feedback(
                                        duplicate_query,
                                        previous,
                                    ),
                                )
                            )
                            continue
                        if rag_calls >= self.max_rag_calls_per_turn:
                            duplicate_count += 1
                            completed_requested_tools.add("knowledge_search")
                            messages.append(
                                ChatMessage(
                                    role=ChatRole.TOOL,
                                    tool_call_id=tool_call.id,
                                    content=_rag_limit_feedback(
                                        self.max_rag_calls_per_turn
                                    ),
                                )
                            )
                            continue
                if signature is not None and signature in executed_calls:
                    duplicate_count += 1
                    previous = existing_evidence.get(signature)
                    if previous is not None:
                        if previous.evidence_id not in reused_evidence_ids:
                            reused_evidence_ids.append(previous.evidence_id)
                        completed_requested_tools.add(tool_call.function.name)
                        if tool_call.function.name == "knowledge_search":
                            sources = _merge_sources(sources, previous.data)
                    messages.append(
                        ChatMessage(
                            role=ChatRole.TOOL,
                            tool_call_id=tool_call.id,
                            content=_reused_evidence_feedback(previous),
                        )
                    )
                    continue
                if signature is not None:
                    executed_calls.add(signature)
                if rag_query is not None:
                    rag_calls += 1
                    rag_queries.append(rag_query)
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
                        tool_signature=signature,
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
            coverage = coverage_from_observations(
                steps=steps,
                evidence=existing_records,
            )
            sufficiency = assess_evidence_sufficiency(
                user_message,
                coverage,
                diagnostic=diagnostic_turn,
            )
            hypotheses = track_hypotheses(
                steps=steps,
                evidence=existing_records,
            )
            result_metadata.update(
                coverage=coverage,
                evidence_sufficiency=sufficiency,
                hypotheses=hypotheses,
            )
            missing_requested = requested_tools - completed_requested_tools
            if missing_requested:
                if missing_tool_attempts >= 2:
                    return fallback(FallbackReason.FINALIZATION_FAILED)
                next_tools = [
                    tool_schemas[name]
                    for name in sorted(missing_requested)
                ]
                next_tool_choice = "auto"
                missing_tool_attempts += 1
                messages.append(_missing_tools_message(missing_requested))
            elif (
                requested_tools
                and sufficiency.goal is not DiagnosticGoal.FULL_WEB_DIAGNOSIS
            ):
                if diagnostic_turn:
                    messages.append(current_context_message())
                next_tool_choice = "none"
            elif sufficiency.sufficient:
                messages.append(current_context_message())
                next_tool_choice = "none"
            elif duplicate_count == len(response.tool_calls):
                if not sufficiency.sufficient and coverage_prompt_attempts < 2:
                    coverage_prompt_attempts += 1
                    next_tool_choice = "auto"
                    messages.append(_coverage_gap_message(sufficiency, hypotheses))
                else:
                    return fallback(FallbackReason.INVALID_TOOL_LOOP)
            elif any(step.result.success for step in steps):
                messages.append(_coverage_gap_message(sufficiency, hypotheses))

def _reused_evidence_feedback(record: EvidenceRecord | None) -> str:
    if record is None:
        payload = {
            "execution_status": "success",
            "diagnostic_status": "already_observed",
            "summary": "相同工具和参数已在本轮执行，请使用已有证据。",
            "evidence": None,
            "reused": True,
        }
    else:
        payload = {
            "tool": record.tool_name,
            "execution_status": "success" if record.reusable else "error",
            "diagnostic_status": record.status,
            "summary": "复用同一 Session 前一轮的结构化 Tool Evidence。",
            "evidence_id": record.evidence_id,
            "evidence": model_safe_data(record.data),
            "observed_at": record.observed_at.isoformat(),
            "turn_index": record.turn_index,
            "reused": True,
        }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _rag_reuse_feedback(
    previous_query: str,
    record: EvidenceRecord | None,
) -> str:
    payload = {
        "tool": "knowledge_search",
        "execution_status": "success",
        "diagnostic_status": "reference_reused",
        "summary": "该查询与已执行的知识检索近义，复用已有 Knowledge Sources。",
        "previous_query": previous_query,
        "evidence_id": record.evidence_id if record is not None else None,
        "reused": True,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _rag_limit_feedback(limit: int) -> str:
    return json.dumps(
        {
            "tool": "knowledge_search",
            "execution_status": "blocked",
            "diagnostic_status": "rag_turn_limit",
            "summary": f"本轮知识检索已达到 {limit} 次上限，请使用已有来源完成回答。",
            "reused": True,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


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


def _coverage_gap_message(
    sufficiency: EvidenceSufficiency,
    hypotheses: list[Hypothesis],
) -> ChatMessage:
    tool_hints = {
        "network_config": "get_network_info",
        "dns": "dns_lookup",
        "ip_connectivity": "ping_host 检查公网 IP",
        "application": "tcp_check(443) 或 http_check",
        "web_path": "dns_lookup、tcp_check 或 http_check 中的相关项",
        "tcp": "tcp_check",
        "any_network": "与用户现象直接相关的只读检测",
    }
    missing = [
        tool_hints.get(item, item)
        for item in sufficiency.missing_coverage
    ]
    active_hypotheses = [
        {"name": item.name, "status": item.status}
        for item in hypotheses
        if item.status in {"possible", "supported"}
    ]
    return ChatMessage(
        role=ChatRole.SYSTEM,
        content=(
            "DIAGNOSTIC COVERAGE INCOMPLETE：当前证据不足以回答用户的完整目标。"
            f"尚缺覆盖：{json.dumps(missing, ensure_ascii=False)}。"
            f"当前假设：{json.dumps(active_hypotheses, ensure_ascii=False)}。"
            "请仅调用填补缺口所需的最少只读工具；"
            "不得因某一项 abnormal 提前输出最终结论。"
        ),
    )


def _deduplicate_consecutive_lines(content: str) -> str:
    """Drop exact adjacent repeated lines without rewriting model meaning."""

    output: list[str] = []
    previous_nonempty: str | None = None
    for line in content.splitlines():
        normalized = line.strip()
        if normalized and normalized == previous_nonempty:
            continue
        output.append(line)
        previous_nonempty = normalized if normalized else None
    return "\n".join(output).strip()


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
    reason: FallbackReason,
    user_message: str,
    evidence: list[EvidenceRecord],
    status: AgentStatus = AgentStatus.COMPLETED,
    reused_evidence_ids: list[str] | None = None,
    turn_intent: TurnIntent | None = None,
    response_mode: ResponseMode | None = None,
    task_version_advanced: bool = False,
    coverage: DiagnosticCoverage | None = None,
    evidence_sufficiency: EvidenceSufficiency | None = None,
    hypotheses: list[Hypothesis] | None = None,
) -> AgentResult:
    return AgentResult(
        answer=build_intent_fallback(
            intent=turn_intent,
            response_mode=response_mode,
            reason=reason,
            user_message=user_message,
            steps=steps,
            evidence=evidence,
            sources=sources,
            hypotheses=list(hypotheses or ()),
        ),
        status=status,
        tool_rounds=tool_rounds,
        steps=steps,
        sources=sources,
        usage=usage,
        llm_duration_ms=llm_duration_ms,
        reused_evidence_ids=list(reused_evidence_ids or ()),
        turn_intent=turn_intent,
        response_mode=response_mode,
        fallback_reason=reason,
        task_version_advanced=task_version_advanced,
        coverage=coverage or DiagnosticCoverage(),
        evidence_sufficiency=evidence_sufficiency,
        hypotheses=list(hypotheses or ()),
    )


def _sources_from_evidence(
    evidence: list[EvidenceRecord],
) -> list[KnowledgeSource]:
    sources: list[KnowledgeSource] = []
    for record in evidence:
        if record.tool_name == "knowledge_search":
            sources = _merge_sources(sources, record.data)
    return sources


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
