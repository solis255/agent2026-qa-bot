from verification_helpers import waiting_cycle,remote_cycle
from client_snapshot_helpers import import_snapshot,payload
from netpilot.verification.baseline import freeze


def test_bv07_baseline_immutable_after_replacement():
    _,store,sid,owner,_,_,task=waiting_cycle()
    baseline=task.verification_cycles[-1].baseline.model_dump()
    task,_,_=import_snapshot(store,sid,owner,payload())
    assert task.verification_cycles[-1].baseline.model_dump() == baseline
    assert set(baseline["evidence_ids"]).issubset({e.evidence_id for e in task.evidence if e.superseded})
    assert task.verification_cycles[-1].after.snapshot_sequence == 2


def test_baseline_excludes_reference_and_old_task():
    *_,task=remote_cycle();plan=task.remediation_plan
    reference=task.evidence[0].model_copy(update={"evidence_id":"rag","tool_name":"knowledge_search","evidence_origin":"knowledge","status":"reference"})
    old=task.evidence[0].model_copy(update={"evidence_id":"old","task_version":99})
    task.evidence.extend([reference,old]);baseline,_=freeze(task,plan)
    assert "rag" not in baseline.evidence_ids and "old" not in baseline.evidence_ids


def test_trimming_never_deletes_pinned_host_baseline():
    from verification_helpers import host_cycle
    _,store,_,_,_,_,task=host_cycle()
    pinned=set(task.verification_cycles[-1].baseline.evidence_ids)
    store.max_evidence_records=1
    task.evidence.extend(task.evidence[0].model_copy(update={"evidence_id":f"extra-{n}"}) for n in range(5))
    store._trim_evidence(task)
    assert pinned.issubset({e.evidence_id for e in task.evidence})


def test_new_turn_baseline_installed_before_evidence_trim():
    from verification_helpers import host_cycle
    from netpilot.agent.schemas import AgentResult,AgentToolStep,AgentStatus
    from netpilot.tools.schemas import ToolResult,DNSLookupData
    from netpilot.diagnostic_target import binding_for
    _,store,sid,owner,_,_,task=host_cycle()
    store.max_evidence_records=1
    step=AgentToolStep(**binding_for(task.diagnostic_target,"execution_host"),round=1,tool_call_id="new-baseline",
        tool_name="dns_lookup",arguments={"domain":"github.com"},result=ToolResult(success=True,tool="dns_lookup",summary="synthetic new observation",data=DNSLookupData(resolved=False),duration_ms=1))
    cycle=task.verification_cycles[-1]
    cycle=cycle.model_copy(update={"baseline":cycle.baseline.model_copy(update={"evidence_ids":(*cycle.baseline.evidence_ids,step.evidence_id)})})
    result=AgentResult(answer="test",status=AgentStatus.COMPLETED,tool_rounds=1,steps=[step],diagnostic_target=task.diagnostic_target,
        remediation_updated=True,remediation_plan=task.remediation_plan,verification_cycles=[cycle])
    store.begin_turn(sid,owner);store.finish_turn(sid,"test",result.answer,result=result)
    restored=store.task_state(sid,owner)
    assert step.evidence_id in {r.evidence_id for r in restored.evidence}
