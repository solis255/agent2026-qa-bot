"""Structured, in-memory task and Tool evidence state for one Session."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from netpilot.agent.coverage import DiagnosticCoverage, EvidenceSufficiency
from netpilot.agent.evidence import finding_status, json_data
from netpilot.agent.hypotheses import Hypothesis
from netpilot.agent.schemas import AgentToolStep
from netpilot.agent.tool_signature import canonical_tool_signature


EvidenceStatus = Literal[
    "normal",
    "abnormal",
    "reference",
    "error",
    "unsupported",
    "unknown",
]


class EvidenceRecord(BaseModel):
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


class SessionTaskState(BaseModel):
    """Structured task memory kept separately from conversational messages."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    owner_user_id: UUID
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

    def reusable_evidence(self) -> list[EvidenceRecord]:
        return [
            record
            for record in self.evidence
            if record.reusable
            and not record.superseded
            and record.task_version == self.task_version
        ]

    def advance_version(self) -> None:
        """Retain prior observations for comparison but stop reusing them."""

        for record in self.evidence:
            if record.task_version == self.task_version:
                record.superseded = True
        self.task_version += 1
        self.executed_tool_signatures.clear()
        self.coverage = DiagnosticCoverage()
        self.hypotheses.clear()
        self.last_evidence_sufficiency = None


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
    )
    return EvidenceRecord(
        tool_name=step.tool_name,
        arguments=step.arguments,
        tool_signature=signature,
        status=status,
        summary=step.result.summary,
        data=data,
        turn_index=turn_index,
        task_version=task_version,
        reusable=bool(step.result.success),
    )
