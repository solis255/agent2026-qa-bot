"""Structured Agent results and tool execution timeline models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from netpilot.agent.coverage import DiagnosticCoverage, EvidenceSufficiency
from netpilot.agent.hypotheses import Hypothesis
from netpilot.agent.intent import TurnIntent
from netpilot.agent.response_modes import ResponseMode
from netpilot.llm import TokenUsage
from netpilot.rag import KnowledgeSource
from netpilot.tools.schemas import ToolResult


class AgentStatus(str, Enum):
    COMPLETED = "completed"
    MAX_TOOL_ROUNDS = "max_tool_rounds"
    LLM_ERROR = "llm_error"


class FallbackReason(str, Enum):
    """Observable reason for using a deterministic response path."""

    MAX_TOOL_ROUNDS = "max_tool_rounds"
    LLM_EMPTY_RESPONSE = "llm_empty_response"
    INVALID_TOOL_LOOP = "invalid_tool_loop"
    LLM_ERROR = "llm_error"
    FINALIZATION_FAILED = "finalization_failed"


class RegistryExecution(BaseModel):
    """Validated arguments paired with a safe tool result."""

    arguments: dict[str, Any] = Field(default_factory=dict)
    result: ToolResult[Any]


class AgentToolStep(BaseModel):
    """One correlated tool execution exposed to later timeline consumers."""

    round: int = Field(ge=1)
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_signature: str | None = None
    result: ToolResult[Any]


class AgentResult(BaseModel):
    """Final one-shot diagnosis plus its bounded evidence trace."""

    answer: str = Field(min_length=1)
    status: AgentStatus
    tool_rounds: int = Field(ge=0)
    steps: list[AgentToolStep] = Field(default_factory=list)
    sources: list[KnowledgeSource] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    llm_duration_ms: float = Field(default=0, ge=0)
    reused_evidence_ids: list[str] = Field(default_factory=list)
    turn_intent: TurnIntent | None = None
    response_mode: ResponseMode | None = None
    fallback_reason: FallbackReason | None = None
    task_version_advanced: bool = False
    coverage: DiagnosticCoverage = Field(default_factory=DiagnosticCoverage)
    evidence_sufficiency: EvidenceSufficiency | None = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)
