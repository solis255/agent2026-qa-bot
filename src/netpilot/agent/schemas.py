"""Structured Agent results and tool execution timeline models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from netpilot.agent.coverage import DiagnosticCoverage, EvidenceSufficiency
from netpilot.agent.hypotheses import Hypothesis
from netpilot.agent.intent import TurnIntent
from netpilot.agent.response_modes import ResponseMode
from netpilot.agent.reasoning_trace import ReasoningTraceStep
from netpilot.llm import TokenUsage
from netpilot.environment import EnvironmentProfile
from netpilot.conversation_context.models import ContextAcquisitionState, ContextQuestion, DiagnosticReadiness
from netpilot.diagnostic_target import DiagnosticTarget, TargetBinding
from netpilot.rag import KnowledgeSource
from netpilot.tools.schemas import ToolResult
from netpilot.remediation.models import RemediationPlan, RemediationReadiness
from netpilot.verification.models import VerificationCycle


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


class AgentToolStep(TargetBinding):
    """One correlated tool execution exposed to later timeline consumers."""

    purpose: Literal["diagnosis", "verification"] = "diagnosis"
    verification_id: UUID | None = None
    round: int = Field(ge=1)
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_signature: str | None = None
    evidence_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    result: ToolResult[Any]


class AgentResult(BaseModel):
    """Final one-shot diagnosis plus its bounded evidence trace."""

    answer: str = Field(min_length=1)
    remediation_plan: RemediationPlan | None = None
    remediation_plan_history: list[RemediationPlan] = Field(default_factory=list)
    remediation_readiness: RemediationReadiness | None = None
    remediation_updated: bool = False
    resolution_recurred: bool = False
    resolution_user_confirmation: Literal["resolved","improved","not_resolved","unknown"] | None = None
    resolution_support_requested: bool = False
    escalation_requested: bool = False
    verification_cycles: list[VerificationCycle] = Field(default_factory=list)
    environment_profile: EnvironmentProfile | None = None
    ui_action: ContextQuestion | None = None
    context_acquisition: ContextAcquisitionState | None = None
    context_answered: bool = False
    environment_update_only: bool = False
    diagnostic_readiness: DiagnosticReadiness | None = None
    diagnostic_target: DiagnosticTarget | None = None
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
    rag_calls: int = Field(default=0, ge=0)
    knowledge_finalization_attempts: int = Field(default=0, ge=0, le=2)
    knowledge_finalization_failure_kind: str | None = None
    history_context_records: int = Field(default=0, ge=0, le=10)
    task_version_advanced: bool = False
    coverage: DiagnosticCoverage = Field(default_factory=DiagnosticCoverage)
    evidence_sufficiency: EvidenceSufficiency | None = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    reasoning_trace: list[ReasoningTraceStep] = Field(default_factory=list)
    reasoning_summary_llm_used: bool = False
    reasoning_summary_prompt_tokens: int = Field(default=0, ge=0)
    reasoning_summary_completion_tokens: int = Field(default=0, ge=0)
