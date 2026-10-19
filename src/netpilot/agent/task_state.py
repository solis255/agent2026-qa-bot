"""Structured, in-memory task and Tool evidence state for one Session."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from netpilot.environment import EnvironmentProfile
from netpilot.diagnostic_target import DiagnosticTarget, TargetBinding, matches_target
from netpilot.client_snapshot.schemas import ClientSnapshotSummary
from netpilot.remediation.models import RemediationPlan, RemediationReadiness
from netpilot.verification.models import VerificationCycle

from netpilot.agent.coverage import DiagnosticCoverage, EvidenceSufficiency
from netpilot.agent.evidence import finding_status, json_data
from netpilot.agent.hypotheses import Hypothesis
from netpilot.agent.schemas import AgentToolStep
from netpilot.agent.reasoning_trace import ReasoningTraceStep
from netpilot.agent.tool_signature import canonical_tool_signature


EvidenceStatus = Literal[
    "normal",
    "abnormal",
    "reference",
    "error",
    "unsupported",
    "unknown",
]


class EvidenceRecord(TargetBinding):
    """One structured observation retained across turns of the same task."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_signature: str = Field(min_length=3)
    status: EvidenceStatus
    summary: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    turn_index: int = Field(ge=1)
    task_version: int = Field(default=1, ge=1)
    reusable: bool = True
    superseded: bool = False
    evidence_origin: Literal["tool", "client_snapshot", "user", "knowledge"] = "tool"
    snapshot_id: str | None = None
    snapshot_sequence: int | None = None
    ingested_at: datetime | None = None
    expires_at: datetime | None = None
    stale: bool = False
    clock_skew_suspected: bool = False
    purpose: Literal["diagnosis", "verification"] = "diagnosis"
    verification_id: UUID | None = None


class SessionTaskState(BaseModel):
    """Structured task memory kept separately from conversational messages."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    owner_user_id: UUID
    environment_profile: EnvironmentProfile = Field(default_factory=EnvironmentProfile)
    diagnostic_target: DiagnosticTarget = Field(default_factory=DiagnosticTarget)
    last_target_trace_version: int = 0
    last_target_limit_version: int = 0
    last_environment_trace_summary: str | None = None
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    executed_tool_signatures: set[str] = Field(default_factory=set)
    current_issue: str | None = None
    last_turn_intent: str | None = None
    last_response_mode: str | None = None
    last_fallback_reason: str | None = None
    coverage: DiagnosticCoverage = Field(default_factory=DiagnosticCoverage)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    last_evidence_sufficiency: EvidenceSufficiency | None = None
    task_version: int = Field(default=1, ge=1)
    turn_index: int = Field(default=0, ge=0)
    reasoning_trace: list[ReasoningTraceStep] = Field(default_factory=list)
    client_snapshot_summary: ClientSnapshotSummary | None = None
    client_snapshot_id: str | None = None
    snapshot_sequence: int = 0
    pending_snapshot_trace: list[ReasoningTraceStep] = Field(default_factory=list)
    remediation_plan: RemediationPlan | None = None
    remediation_plan_history: list[RemediationPlan] = Field(default_factory=list, max_length=20)
    remediation_plan_version: int = 0
    remediation_symptom: str = Field(default="", max_length=4000)
    remediation_readiness: RemediationReadiness = Field(default_factory=lambda: RemediationReadiness(status="not_ready",reason="尚无修复计划，请先诊断或补充现象。"))
    pending_remediation_trace: list[ReasoningTraceStep] = Field(default_factory=list)
    verification_cycles: list[VerificationCycle] = Field(default_factory=list, max_length=50)
    verification_sequence: int = 0
    verification_tool_steps: list[AgentToolStep] = Field(default_factory=list,max_length=100)

    def reusable_evidence(self) -> list[EvidenceRecord]:
        now = datetime.now(timezone.utc)
        return [
            record.model_copy(update={"stale": now > record.expires_at}) if record.expires_at else record
            for record in self.evidence
            if record.reusable
            and not record.superseded
            and record.task_version == self.task_version
            and matches_target(record, self.diagnostic_target)
        ]

    def advance_version(self) -> None:
        """Retain prior observations for comparison but stop reusing them."""

        for record in self.evidence:
            if record.task_version == self.task_version:
                record.superseded = True
        self.task_version += 1
        from netpilot.remediation.service import supersede
        supersede(self.remediation_plan)
        if self.client_snapshot_summary:
            self.client_snapshot_summary.applicable = False
        if self.diagnostic_target.limitation_code == "client_snapshot_available":
            self.diagnostic_target.limitation_code = "remote_client_not_directly_observable"
        self.executed_tool_signatures.clear()
        self.coverage = DiagnosticCoverage()
        self.hypotheses.clear()
        self.last_evidence_sufficiency = None

        from netpilot.remediation.service import invalidate
        invalidate(self)
        from netpilot.verification.service import invalidate_cycles
        invalidate_cycles(self)

    def set_target(self, target: DiagnosticTarget) -> None:
        self.diagnostic_target = target.model_copy(deep=True)
        active = self.reusable_evidence()
        has_snapshot = any(item.evidence_origin == "client_snapshot" for item in active)
        if self.client_snapshot_summary:
            self.client_snapshot_summary.applicable = has_snapshot
        if not has_snapshot and self.diagnostic_target.limitation_code == "client_snapshot_available":
            self.diagnostic_target.limitation_code = "remote_client_not_directly_observable"
        self.executed_tool_signatures = {item.tool_signature for item in active if item.evidence_origin in {"tool", "knowledge"}}
        from netpilot.agent.coverage import coverage_from_observations
        from netpilot.agent.hypotheses import track_hypotheses
        self.coverage = coverage_from_observations(evidence=active)
        self.hypotheses = track_hypotheses(evidence=active)
        self.last_evidence_sufficiency = None
        from netpilot.remediation.service import invalidate
        invalidate(self)
        from netpilot.verification.service import invalidate_cycles
        invalidate_cycles(self)


def evidence_from_step(
    step: AgentToolStep,
    *,
    turn_index: int,
    task_version: int,
) -> EvidenceRecord:
    """Convert one typed execution step into durable Session evidence."""

    raw_data = json_data(step.result.data)
    data = raw_data if isinstance(raw_data, dict) else (
        {"value": raw_data} if raw_data is not None else {}
    )
    error_code = None
    if step.result.error is not None:
        error_code = str(
            getattr(step.result.error.code, "value", step.result.error.code)
        )
    finding = finding_status(step.tool_name, step.result.success, data, error_code)
    status: EvidenceStatus
    if error_code == "unsupported":
        status = "unsupported"
    elif finding == "inconclusive":
        status = "unknown"
    elif finding == "blocked":
        status = "error"
    elif finding in {"normal", "abnormal", "reference", "error"}:
        status = finding  # type: ignore[assignment]
    else:
        status = "unknown"
    signature = step.tool_signature or canonical_tool_signature(
        step.tool_name,
        step.arguments,
        target_subject=step.target_subject, target_version=step.target_version, execution_scope=step.execution_scope,
    )
    return EvidenceRecord(
        **{key:getattr(step, key) for key in TargetBinding.model_fields},
        evidence_id=step.evidence_id,
        tool_name=step.tool_name,
        arguments=step.arguments,
        tool_signature=signature,
        status=status,
        summary=step.result.summary,
        data=data,
        turn_index=turn_index,
        task_version=task_version,
        reusable=bool(step.result.success),
        purpose=step.purpose, verification_id=step.verification_id,
        evidence_origin="knowledge" if step.tool_name == "knowledge_search" else "tool",
    )
