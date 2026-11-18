"""Rebuild the pending server action before accepting an answer."""

from netpilot.conversation_context.models import ContextAnswer

from .factory import current_context_action


def validate_context_answer(task, answer: ContextAnswer) -> None:
    action = current_context_action(task)
    if action is None or answer.field != action.field or answer.value not in {choice.value for choice in action.choices}:
        raise ValueError("context_answer_not_current")
    if answer.action_id is not None and (
        answer.action_id, answer.task_version, answer.target_version
    ) != (action.action_id, action.task_version, action.target_version):
        raise ValueError("context_answer_not_current")
