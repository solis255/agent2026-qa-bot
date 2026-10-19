"""Validated public API contracts for the NetPilot Web demo."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from netpilot.agent.schemas import AgentStatus
from netpilot.agent.task_state import EvidenceRecord
from netpilot.client_snapshot.schemas import ClientSnapshotSummary
from netpilot.remediation.models import RemediationPlan, RemediationReadiness
from netpilot.verification.models import VerificationCycle
from netpilot.resolution.models import ResolutionRecord, ResolutionTransition
from netpilot.escalation.models import EscalationPackage
from netpilot.agent.reasoning_trace import ReasoningTraceStep
from netpilot.config import ToolMode
from netpilot.environment import EnvironmentProfile, BrowserEnvironmentValues, EnvironmentUpdate, legacy_environment
from netpilot.diagnostic_target import DiagnosticTarget, TargetBinding, TargetSubject, legacy_target
from netpilot.rag import SourceType
from netpilot.rag.schemas import StableSourceRef
from netpilot.tools.custom_scenarios import CustomMockScenario, CustomScenarioBehavior
from netpilot.privacy import RedactionMetadata, PRIVACY_POLICY_VERSION


class HealthResponse(BaseModel):
    """Public service-readiness state; deliberately contains no credentials."""

    model_config = ConfigDict(use_enum_values=True)

    status: Literal["ok"] = "ok"
    llm_configured: bool
    tool_mode: ToolMode
    rag_ready: bool
    history_ready: bool
    reasoning_trace_max_steps: int = Field(default=50, ge=1, le=200)
    client_snapshot_max_bytes: int = Field(default=262144, ge=1024)


class RemediationStateView(BaseModel):
    privacy_metadata: RedactionMetadata | None = None
    privacy_policy_version: str = PRIVACY_POLICY_VERSION
    escalation_packages: list[EscalationPackage] = Field(default_factory=list,max_length=20)
    resolution: ResolutionRecord = Field(default_factory=ResolutionRecord)
    resolution_transitions: list[ResolutionTransition] = Field(default_factory=list,max_length=200)
    verification_cycles: list[VerificationCycle] = Field(default_factory=list,max_length=50)
    verification_evidence: list[EvidenceRecord] = Field(default_factory=list)
    remediation_plan: RemediationPlan | None = None
    remediation_plan_history: list[RemediationPlan] = Field(default_factory=list,max_length=20)
    remediation_readiness: RemediationReadiness | None = None


class SessionResponse(RemediationStateView):
    session_id: UUID
    created_at: datetime
    environment_profile: EnvironmentProfile = Field(default_factory=EnvironmentProfile)
    diagnostic_target: DiagnosticTarget = Field(default_factory=DiagnosticTarget)
    client_snapshot_summary: ClientSnapshotSummary | None = None
    client_evidence: list[EvidenceRecord] = Field(default_factory=list)


class DiagnosticTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    subject: Literal["user_client", "netpilot_host"]


class BrowserEnvironmentRequest(BrowserEnvironmentValues):
    session_id: UUID


class UserEnvironmentRequest(EnvironmentUpdate):
    session_id: UUID


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be empty")
        return normalized


EvidenceStatus = Literal[
    "normal",
    "abnormal",
    "error",
    "inconclusive",
    "blocked",
    "reference",
]


class EvidenceView(TargetBinding):
    evidence_origin: Literal["tool", "client_snapshot", "user", "knowledge"] = "tool"
    observed_at: datetime | None = None
    tool: str
    status: EvidenceStatus
    summary: str


class ToolCallView(TargetBinding):
    purpose: Literal["diagnosis", "verification"] = "diagnosis"
    verification_id: UUID | None = None
    round: int = Field(ge=1)
    tool_call_id: str
    evidence_id: str | None = None
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    success: bool
    finding_status: EvidenceStatus
    summary: str
    data: Any | None = None
    error_code: str | None = None
    duration_ms: int = Field(ge=0)


class SourceView(StableSourceRef):
    title: str
    source: str
    source_type: SourceType
    file: str
    chunk_id: str
    score: float = Field(ge=-1.0, le=1.0)


class DiagnosisView(BaseModel):
    status: AgentStatus
    summary: str
    tool_rounds: int = Field(ge=0)
    evidence: list[EvidenceView] = Field(default_factory=list)
    primary_issue: str = "undetermined"
    confidence: Literal["high", "medium", "low"] = "low"
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class TokenUsageView(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ExecutionMetricsView(BaseModel):
    token_usage: TokenUsageView = Field(default_factory=TokenUsageView)
    llm_duration_ms: float = Field(default=0, ge=0)
    tool_duration_ms: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    turn_intent: str | None = None
    response_mode: str | None = None
    fallback_reason: str | None = None
    rag_calls: int = Field(default=0, ge=0)
    knowledge_finalization_attempts: int = Field(default=0, ge=0)
    knowledge_finalization_failure_kind: str | None = None
    history_context_records: int = Field(default=0, ge=0)
    network_tool_calls: int = Field(default=0, ge=0)
    reasoning_trace_steps: int = Field(default=0, ge=0)
    reasoning_summary_llm_used: bool = False
    reasoning_summary_prompt_tokens: int = Field(default=0, ge=0)
    reasoning_summary_completion_tokens: int = Field(default=0, ge=0)


class ChatResponse(RemediationStateView):
    redacted_user_message: str | None = None
    session_id: UUID
    environment_profile: EnvironmentProfile = Field(default_factory=EnvironmentProfile)
    diagnostic_target: DiagnosticTarget = Field(default_factory=DiagnosticTarget)
    client_snapshot_summary: ClientSnapshotSummary | None = None
    client_evidence: list[EvidenceRecord] = Field(default_factory=list)
    record_id: UUID | None = None
    answer: str
    diagnosis: DiagnosisView
    metrics: ExecutionMetricsView = Field(default_factory=ExecutionMetricsView)
    tool_calls: list[ToolCallView] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)
    reasoning_trace: list[ReasoningTraceStep] = Field(default_factory=list)


class PersistedConversationTurn(BaseModel):
    """One actual completed user/assistant pair in a persisted Session."""

    turn_index: int = Field(ge=1)
    target_subject: TargetSubject = "unknown"
    target_version: int = Field(default=1, ge=1)
    user_message: str = Field(min_length=1, max_length=4000)
    assistant_answer: str = Field(min_length=1)
    created_at: datetime
    turn_intent: str | None = None
    response_mode: str | None = None
    fallback_reason: str | None = None
    knowledge_finalization_failure_kind: str | None = None


def _fill_legacy_conversation(value: dict, *, question_key: str, answer_key: str) -> dict:
    """Recover only the last pair actually present in old snapshots."""

    if "conversation_turns" not in value:
        count = value.get("turn_count", 1)
        metrics = value.get("metrics", {})
        if isinstance(metrics, BaseModel):
            metrics = metrics.model_dump()
        if not isinstance(metrics, dict):
            metrics = {}
        value["conversation_turns"] = [{
            "turn_index": count,
            "user_message": value.get("latest_user_message", value.get(question_key)),
            "assistant_answer": value.get(answer_key),
            "created_at": value.get("updated_at", value.get("created_at")),
            **{key: metrics.get(key) for key in (
                "turn_intent", "response_mode", "fallback_reason",
                "knowledge_finalization_failure_kind",
            )},
        }]
        value["conversation_complete"] = count == 1
    return value


class DiagnosisRecordView(RemediationStateView):
    schema_version: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] = 11
    client_snapshot_summary: ClientSnapshotSummary | None = None
    client_evidence: list[EvidenceRecord] = Field(default_factory=list)
    analyzed_snapshot_id: str | None = None
    environment_profile: EnvironmentProfile = Field(default_factory=legacy_environment)
    diagnostic_target: DiagnosticTarget = Field(default_factory=legacy_target)
    record_id: UUID
    user_id: UUID | None = None
    session_id: UUID
    created_at: datetime
    updated_at: datetime
    turn_count: int = Field(default=1, ge=1)
    user_message: str = Field(min_length=1, max_length=4000)
    latest_user_message: str = Field(min_length=1, max_length=4000)
    answer: str
    diagnosis: DiagnosisView
    metrics: ExecutionMetricsView
    tool_calls: list[ToolCallView] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)
    conversation_turns: list[PersistedConversationTurn] = Field(default_factory=list)
    conversation_complete: bool = True
    reasoning_trace: list[ReasoningTraceStep] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def fill_legacy_session_fields(cls, value: Any) -> Any:
        """Read old turn/session snapshots without inventing missing answers."""

        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized.setdefault("updated_at", normalized.get("created_at"))
        normalized.setdefault("turn_count", 1)
        normalized.setdefault(
            "latest_user_message",
            normalized.get("user_message"),
        )
        return _fill_legacy_conversation(normalized, question_key="user_message", answer_key="answer")

    @model_validator(mode="after")
    def validate_conversation_order(self) -> "DiagnosisRecordView":
        indexes = [turn.turn_index for turn in self.conversation_turns]
        if indexes != sorted(set(indexes)) or any(index > self.turn_count for index in indexes):
            raise ValueError("conversation turn indexes must be ordered, unique and within turn_count")
        if self.conversation_complete and (
            len(indexes) != self.turn_count
            or any(index != expected for expected, index in enumerate(indexes, 1))
        ):
            raise ValueError("complete conversation must contain every completed turn")
        return self


class DiagnosisRecordSummaryView(BaseModel):
    resolution: ResolutionRecord = Field(default_factory=ResolutionRecord)
    client_snapshot_summary: ClientSnapshotSummary | None = None
    record_id: UUID
    session_id: UUID
    created_at: datetime
    updated_at: datetime
    turn_count: int = Field(default=1, ge=1)
    user_message: str
    latest_user_message: str
    answer_preview: str
    status: AgentStatus
    primary_issue: str
    confidence: Literal["high", "medium", "low"]
    metrics: ExecutionMetricsView


class DiagnosisHistoryResponse(BaseModel):
    items: list[DiagnosisRecordSummaryView] = Field(default_factory=list)
    next_cursor: str | None = None


class DiagnosisReportView(RemediationStateView):
    schema_version: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] = 11
    client_snapshot_summary: ClientSnapshotSummary | None = None
    client_evidence: list[EvidenceRecord] = Field(default_factory=list)
    environment_profile: EnvironmentProfile = Field(default_factory=legacy_environment)
    diagnostic_target: DiagnosticTarget = Field(default_factory=legacy_target)
    archived_tool_calls: list[ToolCallView] = Field(default_factory=list)
    report_id: UUID
    record_id: UUID
    session_id: UUID
    generated_at: datetime
    created_at: datetime
    updated_at: datetime
    turn_count: int = Field(default=1, ge=1)
    title: str = "TJU NetPilot 故障诊断报告"
    question: str = Field(min_length=1, max_length=4000)
    latest_user_message: str = Field(min_length=1, max_length=4000)
    conclusion: str
    diagnosis: DiagnosisView
    metrics: ExecutionMetricsView
    tool_calls: list[ToolCallView] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)
    conversation_turns: list[PersistedConversationTurn] = Field(default_factory=list)
    conversation_complete: bool = True
    reasoning_trace: list[ReasoningTraceStep] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def fill_legacy_report_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        normalized.setdefault("created_at", normalized.get("generated_at"))
        normalized.setdefault("updated_at", normalized.get("generated_at"))
        normalized.setdefault("turn_count", 1)
        normalized.setdefault("latest_user_message", normalized.get("question"))
        return _fill_legacy_conversation(normalized, question_key="question", answer_key="conclusion")


class ScenarioOption(BaseModel):
    name: str
    label: str
    description: str
    kind: Literal["built_in", "custom"] = "built_in"
    behavior: CustomScenarioBehavior | None = None


class ScenarioListResponse(BaseModel):
    current: str
    switch_enabled: bool
    custom_count: int = Field(default=0, ge=0)
    custom_limit: int = Field(default=20, ge=1)
    scenarios: list[ScenarioOption]


class ScenarioSwitchResponse(BaseModel):
    current: str
    session_id: UUID
    environment_profile: EnvironmentProfile = Field(default_factory=EnvironmentProfile)
    diagnostic_target: DiagnosticTarget = Field(default_factory=DiagnosticTarget)
    sessions_cleared: int = Field(ge=0)


class CustomScenarioCreateRequest(CustomMockScenario):
    """Public request body with the same strict immutable definition."""


class CustomScenarioDeleteResponse(BaseModel):
    deleted: str
    current: str
    session_id: UUID | None = None
    environment_profile: EnvironmentProfile | None = None
    diagnostic_target: DiagnosticTarget | None = None
    sessions_cleared: int = Field(default=0, ge=0)
