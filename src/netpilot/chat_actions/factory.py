"""Select and project the single current action from committed session state."""

from uuid import uuid5

from netpilot.client_snapshot.check_flow import client_check_action
from netpilot.client_snapshot.check_models import ClientCheckAction
from netpilot.conversation_context.models import ChatUIAction, ContextQuestion
from netpilot.conversation_context.needs import is_unknown
from netpilot.conversation_context.questions import build_context_question
from netpilot.resolution.evaluator import cycle_in_scope, valid_objective
from netpilot.resolution.policy import safe_pending

from .models import (
    RESOLUTION_CHOICES, ChatAction, ClientCheckChatAction, ContextQuestionAction,
    RemediationStepAction, ResolutionConfirmationAction, VerificationAction,
)


def action_scope(task, kind, *references):
    target = task.diagnostic_target
    name = ":".join(str(part) for part in (
        kind, task.task_version, target.subject, target.target_version, *references,
    ))
    return dict(action_id=uuid5(task.session_id, name), session_id=task.session_id,
                task_version=task.task_version, target_subject=target.subject, target_version=target.target_version)


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
        **action_scope(task, "context_question", field),
    )


def _verification_action(task, plan, cycle):
    from netpilot.agent.target_capabilities import evaluate_target_capabilities

    if (task.is_demo or cycle.status != "awaiting_after_evidence" or cycle.after_task_version != task.task_version
            or not plan or plan.status in {"cancelled", "superseded"}
            or (cycle.remediation_plan_id, cycle.remediation_plan_version) != (plan.plan_id, plan.plan_version)
            or (plan.target_subject, plan.target_version) != (cycle.target_subject, cycle.target_version)
            or not any(step.status == "completed" for step in plan.steps)):
        return None
    target = task.diagnostic_target
    # Use the current runtime's bound execution context for presentation.
    # The verification service separately checks the real registry provider.
    provider = {"netpilot_host": "local", "mock_provider": "mock"}.get(target.execution_context, "unavailable")
    capability = evaluate_target_capabilities(target, provider)
    if not ((target.subject == "netpilot_host" and capability.can_use_host_network_tools)
            or (target.subject == "mock_client" and capability.can_use_mock_tools)):
        return None
    return VerificationAction(
        **action_scope(task, "verification", cycle.verification_id, plan.plan_id, plan.plan_version),
        verification_id=cycle.verification_id, verification_sequence=cycle.verification_sequence,
        plan_id=plan.plan_id, plan_version=plan.plan_version,
    )


def build_next_chat_action(task) -> ChatAction | None:
    question = current_context_action(task)
    if question is not None:
        return question
    check = client_check_action(task)
    if check:
        return ClientCheckChatAction(**check.model_dump(), target_subject="user_client")

    target = task.diagnostic_target
    plan = task.remediation_plan
    cycle = task.verification_cycles[-1] if task.verification_cycles else None
    if cycle and not cycle_in_scope(cycle, target, task.task_version):
        cycle = None
    if cycle and cycle.status in {"awaiting_after_evidence", "verifying"}:
        return _verification_action(task, plan, cycle)

    resolution = task.resolution
    current_resolution = (resolution.target_subject, resolution.target_version, resolution.task_version) == (
        target.subject, target.target_version, task.task_version,
    )
    if current_resolution and resolution.state in {"resolved", "escalated"}:
        return None
    if (current_resolution and cycle and cycle.after and cycle.after_task_version == task.task_version
            and cycle.user_observation is None and resolution.user_confirmation == "unknown"
            and resolution.based_on_verification_id == cycle.verification_id
            and (cycle.status == "inconclusive" or (cycle.status == "completed" and valid_objective(
                cycle, task.evidence, target, task_version=task.task_version,
            )))):
        return ResolutionConfirmationAction(
            **action_scope(task, "resolution_confirmation", cycle.verification_id, resolution.state_version),
            verification_id=cycle.verification_id, resolution_state_version=resolution.state_version,
            choices=[{"value": value, "label": label} for value, label in RESOLUTION_CHOICES],
        )

    if (not plan or (plan.target_subject, plan.target_version) != (target.subject, target.target_version)
            or (plan.task_version != task.task_version and not (
                cycle and cycle.after_task_version == task.task_version
                and (plan.plan_id, plan.plan_version) == (cycle.remediation_plan_id, cycle.remediation_plan_version)
            ))
            or (current_resolution and resolution.objective_result == "worsened")):
        return None
    step = next(iter(safe_pending(plan)), None)
    if step is None:
        return None
    return RemediationStepAction(
        **action_scope(task, "remediation_step", plan.plan_id, plan.plan_version, step.step_id),
        plan_id=plan.plan_id, plan_version=plan.plan_version, step_id=step.step_id, step_order=step.order,
        allowed_actions=["complete", "skip", "fail"],
    )


def legacy_chat_action(action: ChatAction | None) -> ChatUIAction | None:
    if action is None or action.type not in {"context_question", "client_check"}:
        return None
    model = ContextQuestion if action.type == "context_question" else ClientCheckAction
    return model.model_validate({key: getattr(action, key) for key in model.model_fields})
