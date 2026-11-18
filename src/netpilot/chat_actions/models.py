"""Versioned, bounded UI data. Actions do not grant execution permissions."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from netpilot.client_snapshot.check_models import ClientCheckAction
from netpilot.conversation_context.models import ContextQuestion
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


ChatAction = Annotated[ContextQuestionAction | ClientCheckChatAction, Field(discriminator="type")]
