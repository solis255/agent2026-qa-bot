"""Convert internal Agent evidence into stable, safe Web API views."""

from __future__ import annotations

from uuid import UUID

from netpilot.agent import AgentResult, AgentToolStep
from netpilot.agent.diagnosis import assess_diagnosis, step_status
from netpilot.agent.evidence import json_data
from netpilot.environment import EnvironmentProfile
from netpilot.diagnostic_target import DiagnosticTarget, TargetBinding, binding_for, matches_target
from netpilot.models import (
    ChatResponse,
    DiagnosisView,
    EvidenceView,
    ExecutionMetricsView,
    SourceView,
    ToolCallView,
    TokenUsageView,
)


def present_chat(session_id: UUID, result: AgentResult) -> ChatResponse:
    tool_calls = [_present_tool_call(step, result.diagnostic_target) for step in result.steps]
    current_steps = [_scope_step(step, result.diagnostic_target) for step in result.steps]
    assessment = assess_diagnosis([step for step in current_steps if result.diagnostic_target is None or result.diagnostic_target.subject == "unknown" or matches_target(step, result.diagnostic_target)])
    evidence = [
        EvidenceView(
            **{key:getattr(tool_call, key) for key in TargetBinding.model_fields},
            tool=tool_call.tool_name,
            status=tool_call.finding_status,
            summary=tool_call.summary,
        )
        for tool_call in tool_calls
        if tool_call.tool_name != "knowledge_search"
        and (result.diagnostic_target is None or result.diagnostic_target.subject == "unknown" or matches_target(tool_call, result.diagnostic_target))
    ]
    return ChatResponse(
        remediation_plan=result.remediation_plan,
        remediation_plan_history=result.remediation_plan_history,
        remediation_readiness=result.remediation_readiness,
        session_id=session_id,
        environment_profile=result.environment_profile or EnvironmentProfile(),
        diagnostic_target=result.diagnostic_target or DiagnosticTarget(),
        answer=result.answer,
        diagnosis=DiagnosisView(
            status=result.status,
            summary=result.answer,
            tool_rounds=result.tool_rounds,
            evidence=evidence,
            primary_issue=assessment.primary_issue,
            confidence=assessment.confidence,
            recommendations=list(assessment.recommendations),
            limitations=list(assessment.limitations),
        ),
        metrics=ExecutionMetricsView(
            token_usage=TokenUsageView(**result.usage.model_dump()),
            llm_duration_ms=round(result.llm_duration_ms, 2),
            tool_duration_ms=sum(item.duration_ms for item in tool_calls),
            tool_calls=len(tool_calls),
            rag_calls=result.rag_calls,
            knowledge_finalization_attempts=result.knowledge_finalization_attempts,
            knowledge_finalization_failure_kind=result.knowledge_finalization_failure_kind,
            history_context_records=result.history_context_records,
            network_tool_calls=sum(call.tool_name != "knowledge_search" for call in tool_calls),
            reasoning_trace_steps=len(result.reasoning_trace),
            reasoning_summary_llm_used=result.reasoning_summary_llm_used,
            reasoning_summary_prompt_tokens=result.reasoning_summary_prompt_tokens,
            reasoning_summary_completion_tokens=result.reasoning_summary_completion_tokens,
            turn_intent=(
                result.turn_intent.value if result.turn_intent is not None else None
            ),
            response_mode=(
                result.response_mode.value if result.response_mode is not None else None
            ),
            fallback_reason=(
                result.fallback_reason.value
                if result.fallback_reason is not None
                else None
            ),
        ),
        tool_calls=tool_calls,
        sources=[SourceView(**source.model_dump(mode="json")) for source in result.sources],
        reasoning_trace=result.reasoning_trace,
    )


def _scope_step(step: AgentToolStep, target: DiagnosticTarget | None = None) -> AgentToolStep:
    if step.target_subject == "unknown" and target is not None and target.subject != "unknown":
        scope = "target_neutral" if step.tool_name == "knowledge_search" else "mock_target" if target.execution_context == "mock_provider" else "execution_host"
        step = step.model_copy(update=binding_for(target, scope))
    return step


def _present_tool_call(step: AgentToolStep, target: DiagnosticTarget | None = None) -> ToolCallView:
    step = _scope_step(step, target)
    result = step.result
    data = json_data(result.data)
    error_code = None
    if result.error is not None:
        error_code = str(getattr(result.error.code, "value", result.error.code))
    return ToolCallView(
        **{key:getattr(step, key) for key in TargetBinding.model_fields},
        round=step.round,
        tool_call_id=step.tool_call_id,
        evidence_id=step.evidence_id,
        tool_name=step.tool_name,
        arguments=step.arguments,
        success=result.success,
        finding_status=step_status(step),
        summary=result.summary,
        data=data,
        error_code=error_code,
        duration_ms=result.duration_ms,
    )
