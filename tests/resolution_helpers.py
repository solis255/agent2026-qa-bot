"""Synthetic snapshots and counted Providers; no real repair or ticket I/O."""
from verification_helpers import waiting_cycle
from client_snapshot_helpers import payload,import_snapshot
from netpilot.resolution.evaluator import ResolutionEvaluator


def finished(name="valid"):
    agent,store,sid,owner,counts,llm,_=waiting_cycle()
    task,_,_=import_snapshot(store,sid,owner,payload(name))
    return agent,store,sid,owner,counts,llm,task


def exhaust(task, status="completed"):
    task.remediation_plan.steps=[s.model_copy(update={"status":status,"outcome":"unknown"}) for s in task.remediation_plan.steps]
    task.remediation_plan.status="completed"
    return task


def evaluate(task,confirmation="unknown",threshold=2,**kwargs):
    return ResolutionEvaluator(threshold).evaluate(task.resolution,task.remediation_plan,task.verification_cycles,confirmation,
        task.hypotheses,task.evidence,task.diagnostic_target,task_version=task.task_version,**kwargs)
