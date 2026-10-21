"""Merge explicit/elicited facts using existing provenance; resume the pending topic."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from netpilot.environment import (extract_environment_updates, merge_environment, EnvironmentProfile,
    USER_FIELDS, OS_LABELS, ACCESS_LABELS, SCOPE_LABELS, bool_label, environment_summary,
    is_environment_update_only)
if TYPE_CHECKING:
    from netpilot.agent.intent import IntentClassification
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
    changed_fields: dict[str, tuple[object, object]]
    environment_transition: bool
    update_only: bool


def environment_confirmation(acquired: AcquiredContext) -> str:
    """Use only post-merge values; never let model prose acknowledge a write."""
    labels = {"os_family":"操作系统", "network_access":"接入方式", "vpn_enabled":"VPN", "proxy_enabled":"代理", "affected_scope":"影响范围", "os_version":"系统版本"}
    parts = []
    for name, (old, new) in acquired.changed_fields.items():
        if name not in labels or (name == "os_version" and new is None):
            continue
        values = {"os_family":OS_LABELS, "network_access":ACCESS_LABELS, "affected_scope":SCOPE_LABELS}.get(name)
        before = values.get(old, "未知") if values else bool_label(old) if name.endswith("_enabled") else str(old or "未知")
        after = values.get(new, "未知") if values else bool_label(new) if name.endswith("_enabled") else str(new or "未知")
        parts.append(f"{labels[name]}已从“{before}”改为“{after}”")
    if parts:
        return "已更新当前环境：" + "；".join(parts) + "。环境信息不是网络检测证据。"
    return "尚未确认新的环境变化。当前记录：" + environment_summary(acquired.environment) + "。"


def acquire_context(message, environment, state, *, context_answer=None, has_evidence=False,
                    task_version=1, target_version=1, host_target=False, resume_message=None):
    # Import at call time so this independent module can be imported without
    # re-entering agent.__init__ -> orchestrator -> acquisition during startup.
    from netpilot.agent.intent import classify_turn_intent, TurnIntent
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
        if answer.field == "os_family" and context_answer is None:
            # The allowlisted short answer also carries an explicitly stated
            # version (Win11 / Windows 11); it is not inferred from the server.
            updates.update(extract_environment_updates("我用 " + message).model_dump(exclude_unset=True))
    before = environment
    environment = merge_environment(environment, updates, source="user")
    changed = {name:(getattr(before,name), getattr(environment,name)) for name in sorted(USER_FIELDS)
               if getattr(before,name) != getattr(environment,name)}
    transition = any(name in {"os_family", "network_access", "vpn_enabled", "proxy_enabled"}
                     and old not in (None, "unknown") and new not in (None, "unknown")
                     for name,(old,new) in changed.items())
    update_only = is_environment_update_only(message) and not answer
    if transition:
        state = ContextAcquisitionState(task_version=task_version+1, target_version=target_version, topic=state.topic)
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
    if transition and classification.intent in {TurnIntent.GENERAL_QUESTION, TurnIntent.DIAGNOSE, TurnIntent.CLARIFY, TurnIntent.COMPARE, TurnIntent.STATE_CHANGED}:
        classification = classification.model_copy(update={"intent":TurnIntent.STATE_CHANGED, "reason":"known_environment_values_changed"})
    elif classification.reason == "explicit_environment_transition":
        # A transition verb alone does not prove a known environment changed.
        classification = classification.model_copy(update={"intent":TurnIntent.GENERAL_QUESTION if update_only else TurnIntent.DIAGNOSE,
                                                          "needs_tools":not update_only, "reason":"initial_or_unchanged_environment"})
    topic = context_topic(classification.intent, effective)
    if topic: state.topic = topic
    assessment = assess_environment_need(classification.intent, effective, environment, state,
                                         has_evidence=has_evidence and not transition, host_target=host_target)
    question = plan_context_question(assessment, environment, state)
    if question:
        if question.field not in state.asked_fields: state.asked_fields.append(question.field)
        state.last_question_field = question.field
    return AcquiredContext(environment, state, effective, classification, question, replied, changed, transition, update_only)
