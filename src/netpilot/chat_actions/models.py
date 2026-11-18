"""Versioned, bounded UI data. Actions do not grant execution permissions."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from netpilot.client_snapshot.check_models import ClientCheckAction
from netpilot.conversation_context.models import ContextChoice, ContextQuestion
from netpilot.conversation_context.questions import LABELS, QUESTIONS
from netpilot.diagnostic_target import TargetSubject


class ChatActionScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    action_id: UUID
    session_id: UUID
    task_version: int = Field(ge=1, strict=True)
    target_subject: TargetSubject
    target_version: int = Field(ge=1, strict=True)

    @field_validator("schema_version", mode="before")
    @classmethod
    def require_integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value


class ContextQuestionAction(ChatActionScope, ContextQuestion):
    @model_validator(mode="after")
    def validate_templates(self):
        labels = LABELS[self.field]
        if self.question != QUESTIONS[self.field] or any(labels.get(choice.value) != choice.label for choice in self.choices):
            raise ValueError("context action must use the fixed question and choice labels")
        return self


class ClientCheckChatAction(ChatActionScope, ClientCheckAction):
    target_subject: Literal["user_client"]


class RemediationStepAction(ChatActionScope):
    type: Literal["remediation_step"] = "remediation_step"
    plan_id: UUID
    plan_version: int = Field(ge=1, strict=True)
    step_id: UUID
    step_order: int = Field(ge=1, strict=True)
    allowed_actions: list[Literal["complete", "skip", "fail"]] = Field(min_length=1, max_length=3)


class VerificationAction(ChatActionScope):
    type: Literal["verification"] = "verification"
    mode: Literal["start"] = "start"
    target_subject: Literal["netpilot_host", "mock_client"]
    verification_id: UUID
    verification_sequence: int = Field(ge=1, strict=True)
    plan_id: UUID
    plan_version: int = Field(ge=1, strict=True)


RESOLUTION_QUESTION = "刚才遇到的网络问题，现在有什么变化？"
RESOLUTION_CHOICES = (
    ("resolved", "已经恢复正常"),
    ("improved", "有改善，但还没有完全恢复"),
    ("not_resolved", "还是无法正常使用"),
    ("unknown", "暂时无法确定"),
)


class ResolutionConfirmationAction(ChatActionScope):
    type: Literal["resolution_confirmation"] = "resolution_confirmation"
    verification_id: UUID
    resolution_state_version: int = Field(ge=1, strict=True)
    question: Literal[RESOLUTION_QUESTION] = RESOLUTION_QUESTION
    choices: list[ContextChoice] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def fixed_choices(self):
        if tuple((choice.value, choice.label) for choice in self.choices) != RESOLUTION_CHOICES:
            raise ValueError("resolution confirmation must use the fixed choices")
        return self


ChatAction = Annotated[
    ContextQuestionAction | ClientCheckChatAction | RemediationStepAction | VerificationAction | ResolutionConfirmationAction,
    Field(discriminator="type"),
]
