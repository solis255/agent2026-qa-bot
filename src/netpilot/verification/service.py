"""Session lifecycle, snapshot binding and bounded read-only host refresh."""
import json
from uuid import uuid4

from netpilot.remediation.models import utcnow
from netpilot.verification.baseline import eligible, evidence_set, freeze, metric_value
from netpilot.verification.diff import compare
from netpilot.verification.evaluator import VerificationEvaluator
from netpilot.verification.models import VerificationCycle

ACTIVE = {"baseline_ready", "awaiting_after_evidence", "verifying"}


def emit(task, title, summary, cycle, phase):
    from netpilot.agent.reasoning_trace import ReasoningTraceStep, merge_reasoning_trace
    event = ReasoningTraceStep(step_index=max((e.step_index for e in task.reasoning_trace), default=0)+1,
        event_origin="verification",phase="decision",title=title,summary=summary,
        decision=f"verification:{cycle.verification_sequence}:{phase}",evidence_ids=[*cycle.baseline.evidence_ids,*(cycle.after.evidence_ids if cycle.after else ())],
        turn_index=max(1,task.turn_index),task_version=task.task_version)
    task.reasoning_trace = merge_reasoning_trace(task.reasoning_trace,[event])
    return event


def invalidate_cycles(task):
    plan = task.remediation_plan
    for cycle in task.verification_cycles:
        if cycle.status not in ACTIVE: continue
        if (cycle.target_subject,cycle.target_version) != (task.diagnostic_target.subject,task.diagnostic_target.target_version) or not plan or plan.status in {"superseded","cancelled"} or cycle.remediation_plan_id != plan.plan_id or task.task_version not in {cycle.baseline.task_version, cycle.after_task_version}:
            cycle.status = "superseded"; cycle.updated_at = utcnow()


def protects_plan(task, plan):
    """A verification-owned task bump/After replacement is not a new repair plan."""
    if not task.verification_cycles: return False
    cycle = task.verification_cycles[-1]
    if cycle.remediation_plan_id != plan.plan_id or cycle.status in {"superseded","failed"}: return False
    if (cycle.target_subject,cycle.target_version) != (task.diagnostic_target.subject,task.diagnostic_target.target_version): return False
    if task.task_version not in {cycle.baseline.task_version,cycle.after_task_version}: return False
    from netpilot.remediation.planner import environment_key
    if plan.environment_key != environment_key(task.environment_profile): return False
    if cycle.status == "awaiting_after_evidence": return True
    if cycle.status == "baseline_ready" and cycle.baseline.task_version != plan.task_version:
        return {r.evidence_id for r in eligible(task)} == set(cycle.baseline.evidence_ids)
    if cycle.after:
        if cycle.after.stale: return False
        ids = set(cycle.after.evidence_ids)
        return all(r.evidence_id in ids for r in eligible(task))
    return False


def ensure_baseline(task, *, reverify=False, max_cycles=10):
    invalidate_cycles(task)
    plan = task.remediation_plan
    if not plan or plan.status in {"superseded","cancelled"}: raise ValueError("plan_not_current")
    previous = task.verification_cycles[-1] if task.verification_cycles else None
    if previous and previous.remediation_plan_id == plan.plan_id and previous.status != "superseded" and not reverify:
        return previous, []
    if previous and previous.status in ACTIVE:
        if reverify and previous.status != "baseline_ready": raise ValueError("verification_already_active")
        previous.status = "superseded"
    baseline,checks = freeze(task,plan)
    task.verification_sequence += 1
    cycle = VerificationCycle(verification_sequence=task.verification_sequence,target_subject=plan.target_subject,target_version=plan.target_version,
        remediation_plan_id=plan.plan_id,remediation_plan_version=plan.plan_version,baseline=baseline,checks=checks)
    task.verification_cycles = [*task.verification_cycles,cycle][-max_cycles:]
    return cycle,[emit(task,"记录修复前基线",f"已保存 {len(checks)} 个同对象指标作为修复前对照；基线引用冻结，不随快照替换而覆盖。",cycle,"baseline")]


def activate(task, cycle, *, step_id=None):
    if step_id and cycle.status == "awaiting_after_evidence" and step_id not in cycle.remediation_step_ids:
        cycle.remediation_step_ids = [*cycle.remediation_step_ids,step_id]
    if cycle.status != "baseline_ready": return []
    if step_id: cycle.remediation_step_ids = [step_id]
    # Intentionally preserve this repair plan; ordinary advance_version still
    # supersedes plans/cycles. This is the one verification-owned refresh scope.
    for record in task.evidence:
        if record.task_version == task.task_version: record.superseded = True
    task.task_version += 1
    task.executed_tool_signatures.clear()
    from netpilot.agent.coverage import DiagnosticCoverage
    task.coverage = DiagnosticCoverage(); task.hypotheses.clear(); task.last_evidence_sufficiency = None
    if task.client_snapshot_summary: task.client_snapshot_summary.applicable = False
    cycle.after_task_version = task.task_version
    cycle.status = "awaiting_after_evidence"; cycle.updated_at = utcnow()
    cycle.result_summary = "请重新运行 Windows 客户端诊断脚本并上传新快照。" if cycle.target_subject == "user_client" else "请点击开始验证，只重测与基线直接相关的只读指标。"
    return [emit(task,"开始修复后验证","用户声明完成修复步骤，进入新的 task_version；等待修复后证据，不据此判定改善。",cycle,"start")]


def complete(task, cycle, records, *, captured_at=None):
    cycle.status = "verifying"
    cycle.after = evidence_set(records, task.task_version, captured_at=captured_at)
    cycle.diffs = compare(cycle.checks,records,stale=cycle.baseline.stale or cycle.after.stale)
    cycle.result,cycle.result_summary = VerificationEvaluator().evaluate(cycle)
    cycle.status = "inconclusive" if cycle.result == "inconclusive" else "completed"
    cycle.completed_at = utcnow(); cycle.updated_at = cycle.completed_at
    return [emit(task,"完成修复前后对比",f"Verification={cycle.result}。{cycle.result_summary}",cycle,"complete")]


def bind_snapshot(task, records):
    # Environment/plan updates can precede snapshot import without a Session
    # GET in between. Never let After data revive an invalidated waiting cycle.
    invalidate_cycles(task)
    if not task.verification_cycles: return []
    cycle = task.verification_cycles[-1]
    if cycle.status != "awaiting_after_evidence" or cycle.target_subject != "user_client": return []
    if (task.diagnostic_target.subject,task.diagnostic_target.target_version,task.task_version) != (cycle.target_subject,cycle.target_version,cycle.after_task_version): return []
    if any(r.target_subject != "user_client" or r.target_version != cycle.target_version or r.evidence_origin != "client_snapshot" or r.execution_scope != "client_snapshot" or r.task_version != cycle.after_task_version for r in records): return []
    if not records or any(r.observed_at <= cycle.baseline.captured_at for r in records):
        cycle.result_summary = "该快照生成时间不晚于修复前基线，无法用于修复后验证。"
        return []
    return complete(task,cycle,records,captured_at=records[0].observed_at)


def host_refresh(task, cycle, registry):
    return _readonly_refresh(task,cycle,registry,mock=False)


def mock_refresh(task, cycle, registry):
    """Simulation-only counterpart, never permits a Local host handler."""
    return _readonly_refresh(task,cycle,registry,mock=True)


def _readonly_refresh(task, cycle, registry, *, mock):
    from netpilot.agent.target_capabilities import evaluate_target_capabilities
    from netpilot.agent.schemas import AgentToolStep
    from netpilot.agent.task_state import evidence_from_step
    from netpilot.diagnostic_target import binding_for
    capability = evaluate_target_capabilities(task.diagnostic_target,registry.provider_kind)
    subject="mock_client" if mock else "netpilot_host"
    scope="mock_target" if mock else "execution_host"
    if task.diagnostic_target.subject != subject or not (capability.can_use_mock_tools if mock else capability.can_use_host_network_tools): raise ValueError("host_verification_forbidden")
    if cycle.status in {"completed","inconclusive","failed"}: return []
    if cycle.status != "awaiting_after_evidence": raise ValueError("verification_not_waiting")
    baseline_ids = set(cycle.baseline.evidence_ids)
    critical_keys = {(c.metric,c.target) for c in cycle.checks if c.importance == "critical"}
    selected = [r for r in task.evidence if r.evidence_id in baseline_ids and r.target_subject == subject and r.target_version == cycle.target_version and r.execution_scope == scope and r.evidence_origin == "tool" and metric_value(r) and metric_value(r)[:2] in critical_keys][:10]
    records,seen = [],set()
    try:
        for record in selected:
            if record.tool_name not in {"dns_lookup","ping_host","tcp_check","http_check","get_network_info"}: continue
            if not metric_value(record) or record.tool_signature in seen: continue
            seen.add(record.tool_signature)
            # Arguments are ONLY baseline arguments. Registry revalidates all
            # inputs and provider security policy (including HTTP SSRF checks).
            execution = registry.execute(record.tool_name,json.dumps(record.arguments),target=task.diagnostic_target)
            step = AgentToolStep(**binding_for(task.diagnostic_target,scope),round=1,
                tool_call_id=f"verification-{uuid4()}",tool_name=record.tool_name,arguments=execution.arguments,
                result=execution.result,purpose="verification",verification_id=cycle.verification_id)
            after = evidence_from_step(step,turn_index=max(1,task.turn_index),task_version=task.task_version)
            task.verification_tool_steps = [*task.verification_tool_steps,step][-100:]
            after.purpose = "verification"; after.verification_id = cycle.verification_id
            records.append(after); task.evidence.append(after)
            task.executed_tool_signatures.add(after.tool_signature)
            if execution.result.error and execution.result.error.code == "execution_error":
                raise RuntimeError("verification_process_failed")
    except Exception:
        cycle.status = "failed"; cycle.result = "unknown"; cycle.result_summary = "验证流程发生内部异常，未得出网络是否改善的结论。"; cycle.updated_at = utcnow()
        return [emit(task,"修复后验证流程失败",cycle.result_summary,cycle,"failed")]
    return complete(task,cycle,records)


def context(cycles, target=None, task_version=None):
    lines = ["VERIFICATION STATUS"]
    if not cycles: return "\n".join([*lines,"- none"])
    cycle = cycles[-1]
    mismatch = target and ((target.subject,target.target_version) != (cycle.target_subject,cycle.target_version) or task_version not in {cycle.baseline.task_version,cycle.after_task_version})
    lines.extend([f"- Sequence: {cycle.verification_sequence}; status: {'superseded' if mismatch else cycle.status}",
        f"- Baseline task version: {cycle.baseline.task_version}; After task version: {cycle.after_task_version}",f"- Result: {cycle.result}; target: {cycle.target_subject} v{cycle.target_version}"])
    lines.extend(f"- {d.metric} {d.target or ''}: {d.before or '未知'} → {d.after or '未知'} ({d.change})" for d in cycle.diffs[:10])
    if cycle.user_observation: lines.append(f"- User observation (subjective): {cycle.user_observation.symptom_status}")
    lines.append("Verification is not Resolution. Superseded cycles are historical. User observation is not objective evidence. Do not infer recovery from stale/error/unsupported.")
    return "\n".join(lines)
