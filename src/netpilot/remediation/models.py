"""Bounded remediation contracts; no commands or risk overrides from clients."""
from datetime import datetime, timezone
import re
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from netpilot.diagnostic_target import TargetSubject


def utcnow():
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RemediationReadiness(StrictModel):
    status: Literal["ready", "limited", "not_ready"]
    reason: str = Field(min_length=1, max_length=800)


class RemediationSource(StrictModel):
    source_ref: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str = Field(max_length=300)
    source: str = Field(max_length=2000)
    source_type: Literal["official", "maintainer", "community"]


class RemediationStep(StrictModel):
    step_id: UUID = Field(default_factory=uuid4)
    template_id: str = Field(min_length=1, max_length=80)
    equivalence_key: str = Field(min_length=1, max_length=80)
    order: int = Field(ge=1, le=10)
    title: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=1000)
    instructions: list[str] = Field(min_length=1, max_length=8)
    risk: Literal["low", "medium", "high"] = "low"
    requires_admin: bool = Field(default=False, strict=True)
    changes_system_state: bool = Field(default=False, strict=True)
    reversible: bool = Field(default=True, strict=True)
    rollback_instructions: list[str] = Field(default_factory=list, max_length=8)
    verification: str = Field(min_length=1, max_length=800)
    continue_condition: str | None = Field(default=None, max_length=800)
    applicable_os: list[str] = Field(default_factory=list)
    applicable_targets: list[TargetSubject] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    source_refs: list[str] = Field(default_factory=list, max_length=8)
    status: Literal["pending", "completed", "skipped", "failed"] = "pending"
    outcome: Literal["unknown", "improved", "no_change", "worse"] = "unknown"
    user_note: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def safety_invariants(self):
        if self.changes_system_state and self.reversible and not self.rollback_instructions:
            raise ValueError("reversible changes require rollback instructions")
        if self.status in {"pending", "skipped"} and self.outcome != "unknown":
            raise ValueError("pending/skipped is not an executed outcome")
        return self


class RemediationPlan(StrictModel):
    plan_id: UUID = Field(default_factory=uuid4)
    plan_version: int = Field(ge=1)
    task_version: int = Field(default=1, ge=1)
    target_subject: TargetSubject
    target_version: int = Field(ge=1)
    primary_issue: str | None = Field(default=None, max_length=100)
    diagnosis_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    based_on_evidence_ids: list[str] = Field(default_factory=list, max_length=200)
    based_on_snapshot_id: str | None = None
    status: Literal["proposed", "in_progress", "completed", "superseded", "cancelled"] = "proposed"
    readiness: Literal["ready", "limited", "not_ready"]
    readiness_reason: str = Field(min_length=1, max_length=800)
    context_key: str
    environment_key: str
    symptom: str = Field(default="", max_length=100)
    steps: list[RemediationStep] = Field(default_factory=list, max_length=10)
    sources: list[RemediationSource] = Field(default_factory=list, max_length=8)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def ordered_steps(self):
        if [item.order for item in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("steps must be ordered and contiguous")
        if len({item.equivalence_key for item in self.steps}) != len(self.steps):
            raise ValueError("duplicate actions")
        if self.readiness == "not_ready" and self.steps:
            raise ValueError("not_ready plans cannot contain steps")
        return self


class RemediationRequest(StrictModel):
    session_id: UUID


class StepFeedback(RemediationRequest):
    action: Literal["complete", "skip", "fail"]
    outcome: Literal["unknown", "improved", "no_change", "worse"] = "unknown"
    user_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_outcome(self):
        if self.action == "skip" and self.outcome != "unknown":
            raise ValueError("skipped does not mean executed")
        if self.action == "fail" and self.outcome == "improved":
            raise ValueError("failed cannot mean improved")
        return self

    @field_validator("user_note")
    @classmethod
    def private_note(cls, value):
        if value and re.search(r"(?i)(?:password|api[_-]?key|authorization|cookie|token|secret|密码|密钥)\s*[:=：]|\bBearer\s+|\S+:\S+@|\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", value):
            raise ValueError("do not include credentials or device identifiers")
        return value.strip() or None if value is not None else None
