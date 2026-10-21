"""Bounded context contracts shared by the Agent and chat transport."""
from typing import Literal, Annotated
from netpilot.client_snapshot.check_models import ClientCheckAction

from pydantic import BaseModel, ConfigDict, Field, model_validator
from netpilot.diagnostic_target import TargetSubject

ContextField = Literal["os_family", "network_access", "affected_scope", "vpn_enabled", "proxy_enabled"]
ContextTopic = Literal["connectivity", "web", "campus", "vpn", "proxy", "platform_setup"]
CONTEXT_VALUES = {
    "os_family": ("windows", "macos", "linux", "android", "ios", "unknown"),
    "network_access": ("campus_wifi", "campus_wired", "off_campus", "mobile_hotspot", "unknown"),
    "affected_scope": ("web_only", "all_network", "single_service", "internal_resource", "unknown"),
    "vpn_enabled": ("true", "false", "unknown"),
    "proxy_enabled": ("true", "false", "unknown"),
}


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnvironmentNeedAssessment(ContextModel):
    required: bool
    required_fields: list[ContextField] = Field(default_factory=list, max_length=5)
    missing_fields: list[ContextField] = Field(default_factory=list, max_length=5)
    reason: str = Field(max_length=100)


class ContextChoice(ContextModel):
    value: str = Field(max_length=24)
    label: str = Field(max_length=40)


class ContextQuestion(ContextModel):
    type: Literal["context_question"] = "context_question"
    field: ContextField
    question: str = Field(max_length=200)
    choices: list[ContextChoice] = Field(default_factory=list, max_length=7)
    allow_free_text: bool = True


ChatUIAction = Annotated[ContextQuestion | ClientCheckAction, Field(discriminator="type")]


class ContextAnswer(ContextModel):
    field: ContextField
    value: str = Field(max_length=24, strict=True)

    @model_validator(mode="after")
    def allowlisted_value(self):
        if self.value not in CONTEXT_VALUES[self.field]:
            raise ValueError("unsupported context answer")
        return self


class ContextAcquisitionState(ContextModel):
    # Only allowlisted field/topic names; no message, URL, service, or device ID.
    asked_fields: list[ContextField] = Field(default_factory=list, max_length=5)
    unknown_fields: list[ContextField] = Field(default_factory=list, max_length=5)
    last_question_field: ContextField | None = None
    topic: ContextTopic | None = None
    task_version: int = Field(default=1, ge=1)
    target_version: int = Field(default=1, ge=1)


class DiagnosticReadiness(ContextModel):
    """A bounded routing decision, never an observation or execution permission."""

    state: Literal["knowledge_only", "need_context", "need_client_evidence", "ready"]
    reason: str = Field(min_length=1, max_length=100, pattern=r"^[a-z_]+$")
    missing_context_fields: list[ContextField] = Field(default_factory=list, max_length=5)
    evidence_gap: list[str] = Field(default_factory=list, max_length=8)
    target_subject: TargetSubject
    target_version: int = Field(ge=1)
    task_version: int = Field(default=1, ge=1)
    can_use_host_network_tools: bool = False
    can_use_mock_tools: bool = False
    has_usable_client_evidence: bool = False
    client_evidence_supported: bool | None = None
    recommended_action: Literal["answer_knowledge", "ask_context", "analyze_existing",
                                "run_allowed_diagnostics", "request_client_evidence", "continue_with_limitations"]
