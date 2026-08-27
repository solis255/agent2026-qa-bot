"""Validated public API contracts for the NetPilot Web demo."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from netpilot.agent.schemas import AgentStatus
from netpilot.config import MockScenario, ToolMode
from netpilot.rag import SourceType


class HealthResponse(BaseModel):
    """Public service-readiness state; deliberately contains no credentials."""

    model_config = ConfigDict(use_enum_values=True)

    status: Literal["ok"] = "ok"
    llm_configured: bool
    tool_mode: ToolMode
    rag_ready: bool


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


class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    diagnosis: DiagnosisView
    tool_calls: list[ToolCallView] = Field(default_factory=list)
    sources: list[SourceView] = Field(default_factory=list)


class ScenarioOption(BaseModel):
    name: MockScenario
    label: str
    description: str


class ScenarioListResponse(BaseModel):
    current: MockScenario
    switch_enabled: bool
    scenarios: list[ScenarioOption]


class ScenarioSwitchResponse(BaseModel):
    current: MockScenario
    session_id: UUID
    sessions_cleared: int = Field(ge=0)
