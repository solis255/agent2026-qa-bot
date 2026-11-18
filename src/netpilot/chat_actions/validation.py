"""Rebuild the pending server action before accepting an answer."""

from netpilot.conversation_context.models import ContextAnswer

from .factory import build_next_chat_action, current_context_action


class StaleChatActionError(ValueError):
    message = "这一步已经更新，请根据当前对话中的最新提示继续。"


def validate_chat_action_submission(task, submission, expected_type, **path_ids):
    """Call under the Session lock before mutating the draft or running verification."""
    if submission is None or submission.action_id is None:
        return
    action = build_next_chat_action(task)
    if (action is None or action.type != expected_type or submission.session_id != action.session_id
            or any(getattr(submission, name) != getattr(action, name) for name in submission.action_fields)
            or any(getattr(action, name) != value for name, value in path_ids.items())
            or (action.type == "remediation_step" and submission.action not in action.allowed_actions)):
        raise StaleChatActionError()


def validate_context_answer(task, answer: ContextAnswer) -> None:
    action = current_context_action(task)
    if action is None or answer.field != action.field or answer.value not in {choice.value for choice in action.choices}:
        raise ValueError("context_answer_not_current")
    if answer.action_id is not None and (
        answer.action_id, answer.task_version, answer.target_version
    ) != (action.action_id, action.task_version, action.target_version):
        raise ValueError("context_answer_not_current")
