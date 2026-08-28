"""Validated public API contracts for the NetPilot Web demo."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from netpilot.agent.schemas import AgentStatus
from netpilot.config import ToolMode
from netpilot.rag import SourceType
from netpilot.tools.custom_scenarios import CustomMockScenario, CustomScenarioBehavior


class HealthResponse(BaseModel):
    """Public service-readiness state; deliberately contains no credentials."""

    model_config = ConfigDict(use_enum_values=True)

    status: Literal["ok"] = "ok"
    llm_configured: bool
    tool_mode: ToolMode
    rag_ready: bool
    history_ready: bool


class SessionResponse(BaseModel):
    session_id: UUID
    created_at: datetime


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


class EvidenceView(BaseModel):
    tool: str
    status: EvidenceStatus
    summary: str


class ToolCallView(BaseModel):
    round: int = Field(ge=1)
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    success: bool
    finding_status: EvidenceStatus
    summary: str
    data: Any | None = None
    error_code: str | None = None
    duration_ms: int = Field(ge=0)


class SourceView(BaseModel):
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


class ChatResponse(BaseModel):
    session_id: UUID
    record_id: UUID | None = None
    answer: str
    diagnosis: DiagnosisView
    metrics: ExecutionMetricsView = Field(default_factory=ExecutionMetricsView)
    tool_calls: list[ToolCallView] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)


class DiagnosisRecordView(BaseModel):
    schema_version: Literal[1] = 1
    record_id: UUID
    session_id: UUID
    created_at: datetime
    user_message: str = Field(min_length=1, max_length=4000)
    answer: str
    diagnosis: DiagnosisView
    metrics: ExecutionMetricsView
    tool_calls: list[ToolCallView] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)


class DiagnosisRecordSummaryView(BaseModel):
    record_id: UUID
    session_id: UUID
    created_at: datetime
    user_message: str
    answer_preview: str
    status: AgentStatus
    primary_issue: str
    confidence: Literal["high", "medium", "low"]
    metrics: ExecutionMetricsView


class DiagnosisHistoryResponse(BaseModel):
    items: list[DiagnosisRecordSummaryView] = Field(default_factory=list)
    next_cursor: str | None = None


class DiagnosisReportView(BaseModel):
    schema_version: Literal[1] = 1
    report_id: UUID
    record_id: UUID
    session_id: UUID
    generated_at: datetime
    title: str = "TJU NetPilot 故障诊断报告"
    question: str = Field(min_length=1, max_length=4000)
    conclusion: str
    diagnosis: DiagnosisView
    metrics: ExecutionMetricsView
    tool_calls: list[ToolCallView] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)


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
    sessions_cleared: int = Field(ge=0)


class CustomScenarioCreateRequest(CustomMockScenario):
    """Public request body with the same strict immutable definition."""


class CustomScenarioDeleteResponse(BaseModel):
    deleted: str
    current: str
    session_id: UUID | None = None
    sessions_cleared: int = Field(default=0, ge=0)
