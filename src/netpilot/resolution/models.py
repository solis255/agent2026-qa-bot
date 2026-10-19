"""Bounded, server-owned case state and user-only confirmation contracts."""
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field
from netpilot.diagnostic_target import TargetSubject
from netpilot.remediation.models import StrictModel, utcnow

ResolutionState = Literal["diagnosing", "action_required", "verifying", "resolved", "improved", "unresolved", "escalated"]
UserConfirmation = Literal["resolved", "improved", "not_resolved", "unknown"]
ObjectiveResult = Literal["improved", "unchanged", "worsened", "inconclusive", "unknown"]
STATE_LABELS = {"diagnosing":"诊断中", "action_required":"等待操作", "verifying":"正在验证", "resolved":"已解决",
                "improved":"有改善", "unresolved":"未解决", "escalated":"建议人工处理"}


class ResolutionRecord(StrictModel):
    state: ResolutionState = "diagnosing"
    state_version: int = Field(default=1, ge=1)
    reason_code: str | None = Field(default="initial", max_length=100)
    reason_summary: str | None = Field(default="尚在收集当前对象的诊断依据。", max_length=1600)
    based_on_verification_id: UUID | None = None
    based_on_remediation_plan_id: UUID | None = None
    user_confirmed: bool = False
    user_confirmation: UserConfirmation = "unknown"
    objective_result: ObjectiveResult = "unknown"
    escalation_recommended: bool = False
    escalation_reason: str | None = Field(default=None, max_length=100)
    escalation_summary: str | None = Field(default=None, max_length=1600)
    user_requested_support: bool = False
    target_subject: TargetSubject = "unknown"
    target_version: int = Field(default=1, ge=1)
    task_version: int = Field(default=1, ge=1)
    case_start_task_version: int = Field(default=1, ge=1)
    updated_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    escalated_at: datetime | None = None


class ResolutionTransition(StrictModel):
    transition_id: UUID = Field(default_factory=uuid4)
    from_state: ResolutionState
    to_state: ResolutionState
    state_version: int = Field(ge=2)
    reason_code: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1600)
    verification_id: UUID | None = None
    remediation_plan_id: UUID | None = None
    target_subject: TargetSubject = "unknown"
    target_version: int = Field(default=1, ge=1)
    task_version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utcnow)


class EscalationDecision(StrictModel):
    recommended: bool = False
    reason_code: str | None = None
    summary: str | None = None


class ResolutionRequest(StrictModel):
    session_id: UUID


class ConfirmationRequest(ResolutionRequest):
    status: UserConfirmation
