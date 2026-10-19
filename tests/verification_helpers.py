"""Synthetic evidence, counted Local stand-ins. No real repair or host probing."""
from uuid import UUID
from remediation_helpers import task_with_snapshot
from netpilot.remediation.models import StepFeedback
from netpilot.remediation.service import ensure_plan, update_step
from netpilot.verification.service import ensure_baseline, activate


def remote_cycle():
    agent,store,sid,owner,counts,llm,_ = task_with_snapshot()
    task,events = store.remediation(sid,owner,generate=True)
    return agent,store,sid,owner,counts,llm,task


def waiting_cycle():
    agent,store,sid,owner,counts,llm,task = remote_cycle()
    step=task.remediation_plan.steps[0]
    task,_=store.remediation(sid,owner,step_id=step.step_id,feedback=StepFeedback(session_id=sid,action="complete"))
    return agent,store,sid,owner,counts,llm,task


def complete_step(client,sid,plan):
    response=client.patch(f'/api/session/remediation-plan/steps/{plan["steps"][0]["step_id"]}',json={"session_id":sid,"action":"complete"})
    assert response.status_code == 200,response.text
    return response.json()["verification_cycles"][-1]


def host_cycle():
    from target_helpers import local_session
    from netpilot.agent.task_state import EvidenceRecord
    from netpilot.diagnostic_target import binding_for
    from netpilot.agent.tool_signature import canonical_tool_signature
    agent,store,sid,owner,counts,llm=local_session()
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    task=store._sessions[sid].task_state
    args={"domain":"github.com"}
    task.evidence.append(EvidenceRecord(**binding_for(task.diagnostic_target,"execution_host"),
        tool_name="dns_lookup",arguments=args,tool_signature=canonical_tool_signature("dns_lookup",args,target_subject="netpilot_host",target_version=task.diagnostic_target.target_version),
        status="abnormal",summary="synthetic DNS failure",data={"resolved":False,"addresses":[]},turn_index=1))
    task.executed_tool_signatures.add(task.evidence[0].tool_signature)
    task,_=store.remediation(sid,owner,generate=True)
    task,_=store.remediation(sid,owner,step_id=task.remediation_plan.steps[0].step_id,feedback=StepFeedback(session_id=sid,action="complete"))
    return agent,store,sid,owner,counts,llm,task
