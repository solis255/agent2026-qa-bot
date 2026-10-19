"""Bounded verification contracts. Frozen baselines contain IDs, not raw JSON."""
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, field_validator
from netpilot.remediation.models import StrictModel, StepFeedback, utcnow
from netpilot.diagnostic_target import TargetSubject

Metric = Literal["dns_resolution", "gateway_reachability", "tcp_connectivity", "http_reachability",
                 "network_configuration", "campus_auth", "vpn_state", "proxy_state", "user_observed_symptom"]
Status = Literal["normal", "abnormal", "unknown", "unsupported", "error"]
Change = Literal["improved", "unchanged", "worsened", "not_comparable", "unknown"]


class VerificationEvidenceSet(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    captured_at: datetime
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=200)
    snapshot_id: str | None = None
    snapshot_sequence: int | None = None
    source_kind: Literal["client_snapshot", "host_tools", "user_observation", "mixed", "mock_tools"]
    stale: bool = False
    task_version: int = Field(ge=1)


class VerificationCheck(StrictModel):
    check_id: UUID = Field(default_factory=uuid4)
    metric: Metric = Field(frozen=True)
    target: str | None = Field(default=None, max_length=2100, frozen=True)
    baseline_value: str | None = Field(default=None, max_length=800, frozen=True)
    after_value: str | None = Field(default=None, max_length=800)
    baseline_status: Status = Field(frozen=True)
    after_status: Status | None = None
    importance: Literal["critical", "supporting"] = Field(default="supporting", frozen=True)
    change: Change = "unknown"
    interpretation: str | None = Field(default=None, max_length=1000)


class EvidenceDiff(StrictModel):
    diff_id: UUID = Field(default_factory=uuid4)
    metric: Metric
    target: str | None = None
    before: str | None = None
    after: str | None = None
    change: Change
    interpretation: str = Field(max_length=1000)


class UserVerificationObservation(StrictModel):
    symptom_status: Literal["resolved_by_user_report", "improved_by_user_report", "unchanged_by_user_report", "worsened_by_user_report", "unknown"]
    note: str | None = Field(default=None, max_length=500)
    observed_at: datetime = Field(default_factory=utcnow)
    _private_note = field_validator("note")(StepFeedback.private_note.__func__)


class VerificationCycle(StrictModel):
    verification_id: UUID = Field(default_factory=uuid4)
    verification_sequence: int = Field(ge=1)
    target_subject: TargetSubject
    target_version: int = Field(ge=1)
    remediation_plan_id: UUID
    remediation_plan_version: int = Field(ge=1)
    remediation_step_ids: list[UUID] = Field(default_factory=list, max_length=10)
    status: Literal["baseline_ready", "awaiting_after_evidence", "verifying", "completed", "inconclusive", "failed", "superseded"] = "baseline_ready"
    baseline: VerificationEvidenceSet = Field(frozen=True)
    after: VerificationEvidenceSet | None = None
    checks: list[VerificationCheck] = Field(default_factory=list, max_length=100)
    diffs: list[EvidenceDiff] = Field(default_factory=list, max_length=100)
    result: Literal["improved", "unchanged", "worsened", "inconclusive", "unknown"] = "unknown"
    result_summary: str | None = Field(default=None, max_length=1600)
    user_observation: UserVerificationObservation | None = None
    after_task_version: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class VerificationRequest(StrictModel):
    session_id: UUID
    reverify: bool = Field(default=False, strict=True)


class ObservationRequest(StrictModel):
    session_id: UUID
    symptom_status: Literal["resolved_by_user_report", "improved_by_user_report", "unchanged_by_user_report", "worsened_by_user_report", "unknown"]
    note: str | None = Field(default=None, max_length=500)
    _private_note = field_validator("note")(StepFeedback.private_note.__func__)
