"""Non-fatal Agent integration, isolated from Tool execution and LLM calls."""
from netpilot.agent.reasoning_trace import merge_reasoning_trace
from netpilot.agent.task_state import evidence_from_step
from netpilot.remediation.models import RemediationReadiness
from netpilot.remediation.service import ensure_plan, explicit_remediation, followup_answer, invalidate


def enrich_result(task, result, message, *, max_steps=5, trace_enabled=True, trace_limit=50):
    draft = task.model_copy(deep=True)
    if result.task_version_advanced: draft.advance_version()
    if result.environment_profile: draft.environment_profile = result.environment_profile
    if result.diagnostic_target: draft.set_target(result.diagnostic_target)
    for step in result.steps:
        draft.evidence.append(evidence_from_step(step,turn_index=task.turn_index+1,task_version=draft.task_version))
    draft.reasoning_trace = merge_reasoning_trace(draft.reasoning_trace,result.reasoning_trace,trace_limit)
    invalidate(draft)
    intent = getattr(result.turn_intent,"value",None)
    generate = intent in {"diagnose","state_changed","followup_action"} or explicit_remediation(message)
    if result.resolution_recurred: generate=False
    events = []
    if intent in {"diagnose","state_changed"}:
        draft.remediation_symptom = message
    if generate:
        # After an actual comparison, an explicit next-action request may need
        # a revised plan. Keep the completed verification as history and let
        # the catalog omit completed/skipped equivalences from the new plan.
        if intent == "followup_action" and explicit_remediation(message) and draft.verification_cycles and draft.verification_cycles[-1].after is not None and draft.verification_cycles[-1].status in {"completed","inconclusive"}:
            from netpilot.remediation.service import supersede
            supersede(draft.remediation_plan)
        _, events = ensure_plan(draft,message=message if intent in {"diagnose","state_changed"} else draft.remediation_symptom + " " + message,
                                max_steps=max_steps,sources=result.sources,trace_enabled=trace_enabled,trace_limit=trace_limit)
    updates = {"remediation_plan":draft.remediation_plan,"remediation_plan_history":draft.remediation_plan_history,
               "verification_cycles":draft.verification_cycles,
               "remediation_readiness":draft.remediation_readiness,"remediation_updated":True,
               "reasoning_trace":[*result.reasoning_trace,*events]}
    if intent == "followup_action" and explicit_remediation(message):
        updates["answer"] = followup_answer(draft.remediation_plan)
    return result.model_copy(update=updates)
