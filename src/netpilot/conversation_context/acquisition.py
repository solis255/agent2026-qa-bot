"""Merge explicit/elicited facts using existing provenance; resume the pending topic."""
from dataclasses import dataclass

from netpilot.environment import extract_environment_updates, merge_environment, EnvironmentProfile
from netpilot.agent.intent import classify_turn_intent, IntentClassification
from .models import ContextAcquisitionState, ContextAnswer, ContextQuestion
from .needs import assess_environment_need, context_topic, is_unknown
from .questions import answer_values, free_text_answer, plan_context_question

RESUME_MESSAGES = {
    "web":"网页打不开，请根据目前信息分析。",
    "connectivity":"网络有问题，请诊断当前现象。",
    "campus":"校园网连不上，请根据目前信息分析。",
    "vpn":"VPN 一直失败，请根据目前信息分析。",
    "proxy":"代理连接失败，请根据目前信息分析。",
    "platform_setup":"校园网 VPN 客户端怎么安装？",
}


@dataclass
class AcquiredContext:
    environment: EnvironmentProfile
    state: ContextAcquisitionState
    message: str
    classification: IntentClassification
    question: ContextQuestion | None
    answered: bool


def acquire_context(message, environment, state, *, context_answer=None, has_evidence=False,
                    task_version=1, target_version=1, host_target=False, resume_message=None):
    state = state.model_copy(deep=True)
    if (state.task_version, state.target_version) != (task_version, target_version):
        state = ContextAcquisitionState(task_version=task_version, target_version=target_version)
    updates = extract_environment_updates(message).model_dump(exclude_unset=True)
    pending = state.last_question_field
    answer = context_answer or (free_text_answer(pending, message) if pending else None)
    if context_answer and (context_answer.field != pending or not state.topic):
        raise ValueError("context_answer_not_pending")
    if answer:
        updates.update(answer_values(answer))
    environment = merge_environment(environment, updates, source="user")
    for name in list(state.unknown_fields):
        if not is_unknown(environment, name): state.unknown_fields.remove(name)
    for name in updates:
        if is_unknown(environment, name) and name in {"os_family", "network_access", "affected_scope", "vpn_enabled", "proxy_enabled"} and name not in state.unknown_fields:
            state.unknown_fields.append(name)
    classification = classify_turn_intent(message, has_evidence=has_evidence)
    # A bare choice must continue the question's diagnostic topic, not become
    # an unrelated knowledge query. Explicit new requests keep their own intent.
    replied = bool(answer or (pending and pending in updates))
    effective = RESUME_MESSAGES[state.topic] if replied and state.topic else message
    if replied and state.topic == "platform_setup" and resume_message:
        effective = resume_message
    if replied:
        state.last_question_field = None
        classification = classify_turn_intent(effective, has_evidence=has_evidence)
    elif classification.intent.value in {"knowledge_request", "report_request", "history_analysis", "meta_feedback", "diagnose", "state_changed", "compare"}:
        state.last_question_field = None
    topic = context_topic(classification.intent, effective)
    if topic: state.topic = topic
    assessment = assess_environment_need(classification.intent, effective, environment, state,
                                         has_evidence=has_evidence, host_target=host_target)
    question = plan_context_question(assessment, environment, state)
    if question:
        if question.field not in state.asked_fields: state.asked_fields.append(question.field)
        state.last_question_field = question.field
    return AcquiredContext(environment, state, effective, classification, question, replied)
