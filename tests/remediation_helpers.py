from client_snapshot_helpers import payload, import_snapshot
from target_helpers import local_session, run
from netpilot.remediation.planner import RemediationPlanner


def task_with_snapshot(name="dns_failure", **environment):
    agent,store,sid,owner,counts,llm=local_session()
    if environment: store.update_environment(sid,owner,environment,source="user")
    task,_,_=import_snapshot(store,sid,owner,payload(name))
    return agent,store,sid,owner,counts,llm,task


def build(task, **kwargs):
    return RemediationPlanner().build_plan(task.environment_profile,task.diagnostic_target,
        hypotheses=task.hypotheses,evidence=task.reusable_evidence(),client_snapshot_summary=task.client_snapshot_summary,
        task_version=task.task_version,user_message="网页打不开，怎么解决",**kwargs)
