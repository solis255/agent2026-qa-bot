"""Pure, target/version/freshness-aware decision tree. Never consume LLM state."""
from datetime import datetime, timedelta, timezone

from netpilot.resolution.models import ResolutionRecord
from netpilot.resolution.policy import EscalationPolicy, safe_pending
from netpilot.verification.evaluator import VerificationEvaluator


def cycle_in_scope(cycle, target, task_version=None):
    return ((cycle.target_subject,cycle.target_version) == (target.subject,target.target_version)
            and cycle.status not in {"superseded","failed"}
            and (task_version is None or (task_version == cycle.after_task_version if cycle.after and cycle.status in {"completed","inconclusive"} else task_version in {cycle.baseline.task_version,cycle.after_task_version})))


def valid_objective(cycle, evidence, target, *, task_version=None, historical=False):
    """Revalidate references, origin and capture semantics; a result string is insufficient."""
    if not cycle or not cycle_in_scope(cycle,target,task_version) or not cycle.after or not cycle.after.evidence_ids:
        return False
    if cycle.baseline.stale or cycle.after.stale: return False
    by_id = {r.evidence_id:r for r in evidence}
    now = datetime.now(timezone.utc)
    remote = target.subject == "user_client" and target.relationship_to_netpilot == "remote"
    scope = "client_snapshot" if remote else "mock_target" if target.subject == "mock_client" else "execution_host"
    for side in [cycle.baseline,cycle.after]:
        if not side.evidence_ids: return False
        for eid in side.evidence_ids:
            r = by_id.get(eid)
            if r is None or (r.target_subject,r.target_version,r.task_version) != (target.subject,target.target_version,side.task_version): return False
            if r.execution_scope != scope or r.evidence_origin not in {"tool","client_snapshot"}: return False
            if remote and (r.evidence_origin != "client_snapshot" or r.execution_context != "user_client_snapshot"): return False
            if not remote and r.evidence_origin != "tool": return False
            if scope == "execution_host" and r.execution_context != "netpilot_host": return False
            if r.clock_skew_suspected: return False
            if side is cycle.after and r.observed_at <= cycle.baseline.captured_at: return False
            if not historical and side is cycle.after and (r.stale or r.superseded or (r.expires_at and now > r.expires_at)): return False
    if cycle.after.task_version != cycle.after_task_version: return False
    if cycle.after.task_version <= cycle.baseline.task_version: return False
    if not historical:
        for eid in cycle.after.evidence_ids:
            r=by_id[eid]
            if r.expires_at is None and now-r.observed_at > timedelta(minutes=15): return False
    # Check summaries cannot override the referenced structured observations.
    from netpilot.verification.baseline import metric_value
    from netpilot.verification.diff import compare
    before_records=[by_id[eid] for eid in cycle.baseline.evidence_ids]
    after_records=[by_id[eid] for eid in cycle.after.evidence_ids]
    before_map={metric_value(r)[:2]:r for r in before_records if metric_value(r)}
    for check in cycle.checks:
        if check.importance != "critical": continue
        record=before_map.get((check.metric,check.target))
        if record is None or record.status != check.baseline_status: return False
        expected=check.model_copy(deep=True)
        compare([expected],after_records)
        if (expected.after_status,expected.change) != (check.after_status,check.change): return False
    return True


class ResolutionEvaluator:
    def __init__(self, threshold=2):
        self.policy = EscalationPolicy(threshold)

    def evaluate(self, current_resolution, remediation_plan, verification_cycles, user_confirmation,
                 hypotheses, evidence, diagnostic_target, *, task_version, user_requested=False):
        current = current_resolution
        cycles = [c for c in verification_cycles if cycle_in_scope(c,diagnostic_target)]
        cycle = next((c for c in reversed(cycles) if cycle_in_scope(c,diagnostic_target,task_version)),None)
        plan = remediation_plan if remediation_plan and (remediation_plan.target_subject,remediation_plan.target_version) == (diagnostic_target.subject,diagnostic_target.target_version) and remediation_plan.status not in {"superseded","cancelled"} else None
        if plan and plan.task_version != task_version and not (cycle and cycle.remediation_plan_id == plan.plan_id): plan=None
        pending = safe_pending(plan)
        fresh = valid_objective(cycle,evidence,diagnostic_target,task_version=task_version)
        objective = VerificationEvaluator().objective(cycle)[0] if fresh and cycle and cycle.status in {"completed","inconclusive"} else "inconclusive" if cycle and cycle.after else "unknown"
        valid_cycles = [c for c in cycles if c.baseline.task_version >= current.case_start_task_version and valid_objective(c,evidence,diagnostic_target,historical=True)]
        scoped_records = [r for r in evidence if (r.target_subject,r.target_version,r.task_version) == (diagnostic_target.subject,diagnostic_target.target_version,task_version)
                          and r.evidence_origin in {"tool","client_snapshot"} and not r.superseded and not r.stale and not r.clock_skew_suspected and (not r.expires_at or datetime.now(timezone.utc) <= r.expires_at)]
        scoped_records = [r for r in scoped_records if r.execution_scope == ("client_snapshot" if diagnostic_target.subject == "user_client" and diagnostic_target.relationship_to_netpilot == "remote" else "mock_target" if diagnostic_target.subject == "mock_client" else "execution_host")]
        scoped_records = [r for r in scoped_records if (r.execution_scope == "client_snapshot" and r.evidence_origin == "client_snapshot" and r.execution_context == "user_client_snapshot") or (r.execution_scope == "execution_host" and r.evidence_origin == "tool" and r.execution_context == "netpilot_host") or (r.execution_scope == "mock_target" and r.evidence_origin == "tool" and r.execution_context == "mock_provider")]
        latest_scoped=next((c for c in reversed(verification_cycles) if (c.target_subject,c.target_version) == (diagnostic_target.subject,diagnostic_target.target_version) and task_version in {c.baseline.task_version,c.after_task_version}),None)
        no_observation = bool(plan and any(s.status in {"completed","failed"} for s in plan.steps) and not fresh and latest_scoped and latest_scoped.status not in {"baseline_ready","awaiting_after_evidence","verifying"})
        decision = self.policy.evaluate(plan=plan,cycles=valid_cycles,user_requested=user_requested,hypotheses=hypotheses,evidence=scoped_records,insufficient_observability=no_observation)
        critical = [c for c in cycle.checks if c.importance == "critical"] if cycle else []
        recovered = bool(critical and any(c.baseline_status == "abnormal" for c in critical)
                         and all(c.after_status == "normal" and c.change in {"improved","unchanged"} for c in critical)
                         and not any(c.change == "worsened" for c in cycle.checks))
        active = bool(cycle and (cycle.status in {"awaiting_after_evidence","verifying"} or (cycle.status == "baseline_ready" and cycle.checks and plan and any(s.status == "completed" for s in plan.steps))))
        if user_requested:
            state,reason,summary = "escalated","user_requested",decision.summary
        elif active:
            state,reason,summary = "verifying","awaiting_verification","正在等待修复后证据或进行复核；完成步骤不等于问题解决。"
        elif objective == "improved" and fresh and recovered and user_confirmation == "resolved" and cycle.result == "improved" and cycle.status == "completed":
            state,reason,summary = "resolved","objective_and_user_confirmed","关键异常指标已恢复，客观复核有效，且用户明确确认原始症状消失。"
        elif decision.recommended and (decision.reason_code in {"user_requested","admin_required","infrastructure_suspected","insufficient_observability","user_declined_remaining_steps"}
                                       or (decision.reason_code == "repeated_no_improvement" and not pending)
                                       or (decision.reason_code == "verification_worsened" and not pending)
                                       or (decision.reason_code == "no_safe_remediation_left" and objective not in {"improved","unchanged"})):
            state,reason,summary = "escalated",decision.reason_code,decision.summary
        elif objective == "improved":
            state,reason,summary = "improved","objective_improved_not_confirmed","客观指标有改善，但用户尚未确认完全恢复。" if user_confirmation != "not_resolved" else "客观指标已改善，但用户仍报告原始症状存在；尚未完全解决。"
        elif objective == "worsened":
            state,reason,summary = "unresolved","verification_worsened","关键指标变差，当前流程未解决问题；不表示问题不可修复。"
        elif user_confirmation in {"resolved","improved"}:
            state,reason,summary = "improved","subjective_only","用户报告症状已恢复或改善，但尚缺少一致、有效的客观复核证据。"
        elif objective == "unchanged" and not pending:
            state,reason,summary = "unresolved","verification_unchanged","复核无变化，当前低风险流程尚未解决问题；不表示问题不可修复。"
        elif pending:
            state,reason,summary = "action_required","safe_steps_pending","已有当前对象的低风险手动步骤，等待用户选择执行；不会自动操作。"
        else:
            state,reason,summary = "diagnosing","collecting_evidence","尚在收集当前对象的诊断依据；缺少可用证据时不宣称解决。"
        updates = dict(state=state,reason_code=reason,reason_summary=summary,based_on_verification_id=cycle.verification_id if cycle else None,
            based_on_remediation_plan_id=plan.plan_id if plan else None,user_confirmation=user_confirmation,user_confirmed=user_confirmation != "unknown",
            objective_result=objective,escalation_recommended=decision.recommended,escalation_reason=decision.reason_code,escalation_summary=decision.summary,
            user_requested_support=user_requested,target_subject=diagnostic_target.subject,target_version=diagnostic_target.target_version,task_version=task_version)
        return ResolutionRecord(**{**current.model_dump(),**updates})
