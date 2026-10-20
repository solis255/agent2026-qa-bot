"""Strict, deeply immutable export contracts, separate from diagnostic reports."""
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from netpilot.privacy.models import RedactionMetadata, PRIVACY_POLICY_VERSION


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EscalationPrivacyPolicy(FrozenModel):
    # Mandatory removals cannot be disabled by configuration or API input.
    redact_hostname: Literal[True] = True
    redact_mac: Literal[True] = True
    redact_ssid: Literal[True] = True
    redact_tokens: Literal[True] = True
    redact_cookies: Literal[True] = True
    mask_private_ip: bool = False


class PackageTarget(FrozenModel):
    subject: str
    relationship_to_netpilot: str
    execution_context: str
    target_version: int
    notice: str


class PackageEnvironment(FrozenModel):
    os_family: str
    os_version: str | None = None
    network_access: str
    vpn_enabled: bool | None = None
    proxy_enabled: bool | None = None
    affected_scope: str
    affected_service: str | None = None


class PackageIssue(FrozenModel):
    title: str
    original_symptom: str
    current_symptom: str
    primary_issue: str
    started_at: datetime | None = None
    last_observed_at: datetime | None = None
    turn_count: int = Field(ge=0)


class PackageEvidence(FrozenModel):
    evidence_id: str
    category: str
    status: Literal["normal", "abnormal", "unknown"]
    summary: str
    observed_at: datetime
    target_subject: str
    task_version: int
    origin: str
    stale: bool


class PackageHypothesis(FrozenModel):
    name: str
    state: Literal["supported", "weakened", "excluded", "possible"]
    summary: str
    evidence_ids: tuple[str, ...] = ()


class PackageRemediation(FrozenModel):
    step_id: UUID
    plan_version: int
    title: str
    status: Literal["pending", "completed", "skipped", "failed"]
    outcome: str
    risk: str
    user_note: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PackageVerification(FrozenModel):
    verification_id: UUID
    related_step: tuple[UUID, ...] = ()
    status: str
    result: str
    key_diffs: tuple[str, ...] = ()
    user_observation: str | None = None
    completed_at: datetime | None = None
    historical: bool = False


class PackageResolution(FrozenModel):
    state: str
    state_version: int
    objective_result: str
    user_confirmation: str
    reason_code: str | None = None
    reason_summary: str | None = None


class PackageReason(FrozenModel):
    reason_code: str
    summary: str
    triggered_by: Literal["resolution", "user_request"]


class PackagePrivacy(FrozenModel):
    redacted_fields: tuple[str, ...]
    private_ip_masked: bool
    sensitive_values_removed: bool = True


class EscalationPackage(FrozenModel):
    is_demo: bool = False
    demo_scenario_id: str | None = None
    data_notice: str = ""
    privacy_policy_version: str = PRIVACY_POLICY_VERSION
    privacy_metadata: RedactionMetadata | None = None
    package_id: UUID = Field(default_factory=uuid4)
    package_version: int = Field(ge=1)
    session_id: UUID
    generated_at: datetime
    target: PackageTarget
    environment: PackageEnvironment
    issue: PackageIssue
    evidence_summary: tuple[PackageEvidence, ...] = Field(default=(), max_length=50)
    excluded_or_weakened_hypotheses: tuple[PackageHypothesis, ...] = ()
    remediation_summary: tuple[PackageRemediation, ...] = ()
    verification_summary: tuple[PackageVerification, ...] = ()
    resolution: PackageResolution
    escalation_reason: PackageReason
    recommended_handoff_checks: tuple[str, ...]
    source_refs: tuple[str, ...] = ()
    privacy: PackagePrivacy
    completeness: Literal["complete", "partial", "limited"]
    completeness_notes: tuple[str, ...] = ()
    created_from_state_version: int
    created_from_task_version: int
    created_from_target_version: int
    source_state_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    package_digest: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")


class PackageRequest(FrozenModel):
    session_id: UUID
