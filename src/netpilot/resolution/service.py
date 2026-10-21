"""Explicit lifecycle hooks and audit integration; no Tool, LLM or external I/O."""
import re

from netpilot.remediation.models import utcnow
from netpilot.resolution.models import ResolutionRecord, STATE_LABELS
from netpilot.resolution.evaluator import ResolutionEvaluator, cycle_in_scope
from netpilot.resolution.transitions import transition

OBSERVATIONS = {"resolved_by_user_report":"resolved", "improved_by_user_report":"improved",
                "unchanged_by_user_report":"not_resolved", "worsened_by_user_report":"not_resolved", "unknown":"unknown"}


def user_action(message, *, was_resolved=False):
    """Only unquoted first-person statements; references/questions are not commands."""
    if re.search(r'如果|假如|假设|例如|比如|他说|文档|prompt|["“”‘’`]',message,re.I): return None
    if message.strip().endswith(("?","？")): return None
    text=message.strip().rstrip("。！!？?")
    if was_resolved and re.search(r"(?:刚才|之前|原来).{0,8}(?:好了|恢复|正常).{0,8}(?:现在|又|再次).{0,8}(?:打不开|不通|断网|坏了|不行)",text): return "recurrence"
    if re.fullmatch(r"(?:请|请求|我要|我需要|帮我|请帮我)?(?:转人工|人工支持|人工帮助|人工处理|联系人工支持)",text): return "support"
    if re.fullmatch(r"(?:已经|现在)?(?:好了|恢复了)|(?:问题|网络|网页)(?:现在|已经)?(?:已解决|恢复正常了|恢复了|可以正常打开了)|网页现在可以正常打开了",text): return "resolved"
    if re.fullmatch(r"好多了|有改善|有些改善|部分恢复了",text): return "improved"
    if re.fullmatch(r"网页还是打不开|网页仍然打不开|还没解决|问题仍未解决",text): return "recurrence" if was_resolved else "not_resolved"
    return None


def _commit(container, candidate, *, allow_reopen=False, trace_enabled=True, transition_limit=30, trace_limit=50):
    current=container.resolution
    record,audit=transition(current,candidate,allow_reopen=allow_reopen)
    container.resolution=record
    if audit is None: return []
    container.resolution_transitions=[*container.resolution_transitions,audit][-transition_limit:]
    if not trace_enabled: return []
    from netpilot.agent.reasoning_trace import ReasoningTraceStep,merge_reasoning_trace
    title="确认问题已解决" if record.state == "resolved" else "建议升级人工处理" if record.state == "escalated" else "诊断状态更新"
    step=ReasoningTraceStep(step_index=max((e.step_index for e in container.reasoning_trace),default=0)+1,
        event_origin="resolution",phase="state_change",title=title,summary=f"{STATE_LABELS[audit.from_state]} → {STATE_LABELS[audit.to_state]}：{audit.summary}",
        decision=f"resolution:v{record.state_version}",turn_index=max(1,getattr(container,"turn_index",getattr(container,"turn_count",1))),task_version=record.task_version)
    container.reasoning_trace=merge_reasoning_trace(container.reasoning_trace,[step],trace_limit)
    return [step]


def reopen(container, target, task_version, reason, *, preserve_epoch=False, **options):
    current=container.resolution
    summaries={"target_changed":"诊断对象已切换，旧对象的处理状态仅保留于历史。", "symptom_recurred":"用户明确报告症状复发，已开启新的任务版本并重新收集证据。",
               "task_changed":"问题或环境状态版本已改变，旧结论不能直接用于当前任务。", "user_confirmation_changed":"用户撤回此前完整恢复确认，需要重新收集依据。", "user_requested":"用户请求人工支持，重新打开当前案例以记录人工处理建议。"}
    candidate=ResolutionRecord(state="diagnosing",state_version=current.state_version,reason_code=reason,reason_summary=summaries.get(reason,summaries["task_changed"]),
        target_subject=target.subject,target_version=target.target_version,task_version=task_version,
        case_start_task_version=current.case_start_task_version if preserve_epoch else task_version)
    return _commit(container,candidate,allow_reopen=True,**options)


def sync(task, *, source="turn", confirmation=None, request_support=False, reopen_reason=None,
         threshold=2, transition_limit=30, trace_limit=50, trace_enabled=True):
    options=dict(transition_limit=transition_limit,trace_limit=trace_limit,trace_enabled=trace_enabled)
    events=[]
    current=task.resolution
    target=task.diagnostic_target
    identity_changed=(current.target_subject,current.target_version) != (target.subject,target.target_version)
    task_changed=current.task_version != task.task_version
    if identity_changed or task_changed or reopen_reason:
        verification_bump=source in {"verification","remediation"} and not identity_changed and not reopen_reason
        reason=reopen_reason or ("target_changed" if identity_changed else "task_changed")
        if verification_bump and current.state != "resolved":
            task.resolution=current.model_copy(update={"task_version":task.task_version,"user_confirmation":"unknown","user_confirmed":False,"user_requested_support":False})
        elif not (current.target_subject == "unknown" and current.reason_code == "initial" and current.state == "diagnosing"):
            events.extend(reopen(task,target,task.task_version,reason,preserve_epoch=verification_bump,**options))
        else:
            task.resolution=current.model_copy(update={"target_subject":target.subject,"target_version":target.target_version,"task_version":task.task_version})
        if reopen_reason or identity_changed:
            return events
        current=task.resolution
    cycle=next((c for c in reversed(task.verification_cycles) if cycle_in_scope(c,target,task.task_version)),None)
    if confirmation is None and source in {"verification","remediation"} and cycle and cycle.user_observation:
        # A newly entered 12E observation is a user statement, not model output.
        if cycle.user_observation.observed_at > current.updated_at:
            confirmation=OBSERVATIONS[cycle.user_observation.symptom_status]
    if current.state == "resolved" and (confirmation is not None and confirmation != "resolved"):
        task.advance_version()
        reason="symptom_recurred" if confirmation == "not_resolved" else "user_confirmation_changed"
        events.extend(reopen(task,target,task.task_version,reason,**options))
        task.resolution.user_confirmation=confirmation; task.resolution.user_confirmed=confirmation != "unknown"
        return events
    if current.state == "resolved" and request_support:
        events.extend(reopen(task,target,task.task_version,"user_requested",**options));current=task.resolution
    elif current.state == "resolved" and confirmation in {None,"resolved"}:
        # Resolved is an audited conclusion at its timestamp, not a claim of
        # perpetual freshness. Only explicit recurrence/target/task reopens it.
        return events
    if cycle and current.based_on_verification_id not in {None,cycle.verification_id}:
        current=current.model_copy(update={"user_confirmation":"unknown","user_confirmed":False})
    chosen=confirmation if confirmation is not None else current.user_confirmation
    if confirmation is not None and source == "confirm" and cycle and (chosen != current.user_confirmation or cycle.user_observation is None):
        # Explicit newer user confirmation consistently replaces the old 12E
        # subjective observation; it never changes objective checks/evidence.
        from netpilot.verification.models import UserVerificationObservation
        from netpilot.verification.evaluator import VerificationEvaluator
        status={"resolved":"resolved_by_user_report","improved":"improved_by_user_report","not_resolved":"unchanged_by_user_report","unknown":"unknown"}[chosen]
        cycle.user_observation=UserVerificationObservation(symptom_status=status)
        if cycle.after and cycle.status not in {"failed","superseded"}:
            cycle.result,cycle.result_summary=VerificationEvaluator().evaluate(cycle)
            cycle.status="inconclusive" if cycle.result == "inconclusive" else "completed"
    candidate=ResolutionEvaluator(threshold).evaluate(current,task.remediation_plan,task.verification_cycles,chosen,task.hypotheses,task.evidence,target,
        task_version=task.task_version,user_requested=request_support or current.user_requested_support)
    events.extend(_commit(task,candidate,**options))
    return events


def context(record, target=None, task_version=None):
    if record is None: return "RESOLUTION STATUS\n- State: diagnosing; no recorded conclusion"
    if target and ((record.target_subject,record.target_version) != (target.subject,target.target_version) or (task_version is not None and record.task_version != task_version)):
        return "RESOLUTION STATUS\n- State: diagnosing; prior conclusion belongs to a different target/task"
    return (f"RESOLUTION STATUS\n- State: {record.state}\n- State version: {record.state_version}\n"
            f"- Objective verification: {record.objective_result}\n- User confirmation: {record.user_confirmation}\n"
            f"- Escalation recommended: {str(record.escalation_recommended).lower()}\n- Reason: {record.reason_summary}\n"
            "Authoritative deterministic case state. Do not override it. Escalation is a recommendation, not a submitted ticket. User confirmation is subjective.")


def answer(record):
    return f"当前处理状态：{STATE_LABELS[record.state]}。{record.reason_summary}\n\n客观复核：{record.objective_result}；用户确认：{record.user_confirmation}。人工支持仅为建议，未提交外部工单。"
