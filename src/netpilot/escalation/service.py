"""Idempotent immutable artifacts and compact, public decision summaries."""
from netpilot.escalation.builder import build_package, state_fingerprint
from netpilot.agent.reasoning_trace import ReasoningTraceStep, merge_reasoning_trace


def ensure_package(task, *, max_evidence=12, max_packages=5, policy=None, trace_enabled=True, trace_limit=50):
    fingerprint = state_fingerprint(task,max_evidence=max_evidence,policy=policy)
    if task.escalation_packages and task.escalation_packages[-1].source_state_fingerprint == fingerprint:
        return task.escalation_packages[-1], []
    package = build_package(task,version=task.escalation_package_sequence+1,max_evidence=max_evidence,policy=policy)
    task.escalation_packages = [*task.escalation_packages,package][-max_packages:]
    task.escalation_package_sequence = package.package_version
    events = []
    if trace_enabled:
        summaries=[("生成升级报修材料",f"已生成报修材料 v{package.package_version}，仅包含结构化交接摘要，未提交外部工单。")]
        if package.completeness != "complete":
            summaries.append(("报修材料信息不完整","缺失项见材料完整度说明；不得据此认定未验证的网络状态。"))
        for title,summary in summaries:
            events.append(ReasoningTraceStep(step_index=max((e.step_index for e in task.reasoning_trace),default=0)+len(events)+1,
                event_origin="escalation",phase="decision",title=title,summary=summary,decision=f"escalation:v{package.package_version}",
                turn_index=max(1,task.turn_index),task_version=task.task_version,severity="warning" if package.completeness != "complete" else "info"))
        task.reasoning_trace=merge_reasoning_trace(task.reasoning_trace,events,trace_limit)
    return package,events


def context(packages):
    if not packages: return "ESCALATION PACKAGE STATUS\n- none; no material generated"
    p=packages[-1]
    return f"ESCALATION PACKAGE STATUS\n- Version: {p.package_version}; completeness: {p.completeness}; generated_at: {p.generated_at.isoformat()}\n- Immutable handoff material only; not a submitted ticket."
