"""Convert internal Agent evidence into stable, safe Web API views."""

from __future__ import annotations

from uuid import UUID

from netpilot.agent import AgentResult, AgentToolStep
from netpilot.agent.diagnosis import assess_diagnosis, step_status
from netpilot.agent.evidence import json_data
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
    tool_calls = [_present_tool_call(step) for step in result.steps]
    assessment = assess_diagnosis(result.steps)
    evidence = [
        EvidenceView(
            tool=tool_call.tool_name,
            status=tool_call.finding_status,
            summary=tool_call.summary,
        )
        for tool_call in tool_calls
    ]
    return ChatResponse(
        session_id=session_id,
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
        ),
        tool_calls=tool_calls,
        sources=[SourceView(**source.model_dump(mode="json")) for source in result.sources],
    )


def _present_tool_call(step: AgentToolStep) -> ToolCallView:
    result = step.result
    data = json_data(result.data)
    error_code = None
    if result.error is not None:
        error_code = str(getattr(result.error.code, "value", result.error.code))
    return ToolCallView(
        round=step.round,
        tool_call_id=step.tool_call_id,
        tool_name=step.tool_name,
        arguments=step.arguments,
        success=result.success,
        finding_status=step_status(step),
        summary=result.summary,
        data=data,
        error_code=error_code,
        duration_ms=result.duration_ms,
    )
