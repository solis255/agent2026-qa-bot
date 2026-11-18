"""Optional versions for legacy workflow endpoints and scoped chat submissions."""

from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from netpilot.diagnostic_target import TargetSubject


class WorkflowActionSubmission(BaseModel):
    action_fields: ClassVar[tuple[str, ...]] = (
        "action_id", "task_version", "target_subject", "target_version",
    )
    action_id: UUID | None = None
    task_version: int | None = Field(default=None, ge=1, strict=True)
    target_subject: TargetSubject | None = None
    target_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def complete_action_scope(self):
        if self.model_fields_set.intersection(self.action_fields) and any(
            getattr(self, field) is None for field in self.action_fields
        ):
            raise ValueError("incomplete chat action scope")
        return self


class PlanActionSubmission(WorkflowActionSubmission):
    action_fields = (*WorkflowActionSubmission.action_fields, "plan_id", "plan_version")
    plan_id: UUID | None = None
    plan_version: int | None = Field(default=None, ge=1, strict=True)


class ResolutionActionSubmission(WorkflowActionSubmission):
    action_fields = (*WorkflowActionSubmission.action_fields, "verification_id", "resolution_state_version")
    verification_id: UUID | None = None
    resolution_state_version: int | None = Field(default=None, ge=1, strict=True)
