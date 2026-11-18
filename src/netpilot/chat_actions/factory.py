"""Select and project the single current action from committed session state."""

from uuid import uuid5

from netpilot.client_snapshot.check_flow import client_check_action
from netpilot.client_snapshot.check_models import ClientCheckAction
from netpilot.conversation_context.models import ChatUIAction, ContextQuestion
from netpilot.conversation_context.needs import is_unknown
from netpilot.conversation_context.questions import build_context_question

from .models import ChatAction, ClientCheckChatAction, ContextQuestionAction


def current_context_action(task) -> ContextQuestionAction | None:
    acquisition = task.context_acquisition
    field = acquisition.last_question_field
    target = task.diagnostic_target
    readiness = task.last_diagnostic_readiness
    versions = (task.task_version, target.target_version)
    if (
        not field or not acquisition.topic or field not in acquisition.asked_fields
        or not is_unknown(task.environment_profile, field)
        or (acquisition.task_version, acquisition.target_version) != versions
        or readiness is None or readiness.state != "need_context"
        or readiness.target_subject != target.subject
        or (readiness.task_version, readiness.target_version) != versions
        or field not in readiness.missing_context_fields
    ):
        return None
    return ContextQuestionAction(
        **build_context_question(field).model_dump(),
        action_id=uuid5(task.session_id, f"context_question:{task.task_version}:{target.subject}:{target.target_version}:{field}"),
        session_id=task.session_id, task_version=task.task_version,
        target_subject=target.subject, target_version=target.target_version,
    )


def build_next_chat_action(task) -> ChatAction | None:
    question = current_context_action(task)
    if question is not None:
        return question
    check = client_check_action(task)
    return ClientCheckChatAction(**check.model_dump(), target_subject="user_client") if check else None


def legacy_chat_action(action: ChatAction | None) -> ChatUIAction | None:
    if action is None:
        return None
    model = ContextQuestion if action.type == "context_question" else ClientCheckAction
    return model.model_validate({key: getattr(action, key) for key in model.model_fields})
