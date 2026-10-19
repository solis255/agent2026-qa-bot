import pytest
from verification_helpers import waiting_cycle,host_cycle
from netpilot.verification.service import host_refresh,ensure_baseline
from netpilot.verification.baseline import freeze


def test_bv05_remote_host_tool_calls_zero_even_explicit_attempt():
    agent,_,_,_,counts,_,task=waiting_cycle()
    with pytest.raises(ValueError):host_refresh(task,task.verification_cycles[-1],agent.registry)
    assert sum(counts.values()) == 0


def test_bv12_version_bump_preserves_target_and_idempotent_activation():
    from netpilot.verification.service import activate
    *_,task=waiting_cycle();cycle=task.verification_cycles[-1]
    assert task.task_version == 2 and task.diagnostic_target.target_version == 1
    activate(task,cycle)
    assert task.task_version == 2


def test_bv13_old_target_and_spoofed_host_excluded():
    *_,task=waiting_cycle()
    bad=task.evidence[1].model_copy(update={"evidence_id":"bad","superseded":False,"task_version":2,"execution_scope":"execution_host","evidence_origin":"tool","tool_name":"dns_lookup"})
    task.evidence.append(bad)
    baseline,_=freeze(task,task.remediation_plan)
    assert "bad" not in baseline.evidence_ids


@pytest.mark.parametrize("change",["target","plan","task"])
def test_bv14_scope_changes_supersede_active_cycle(change):
    _,store,sid,owner,_,_,task=waiting_cycle()
    if change == "target":store.update_diagnostic_target(sid,owner,"netpilot_host")
    elif change == "task":store.advance_task_version(sid,owner)
    else:
        store._sessions[sid].task_state.remediation_plan.status="superseded"
    assert store.task_state(sid,owner).verification_cycles[-1].status == "superseded"


def test_bv06_bv15_host_exact_refresh_and_duplicate():
    agent,store,sid,owner,counts,_,task=host_cycle()
    cycle=task.verification_cycles[-1]
    task,_=store.verification(sid,owner,action="start",cycle_id=cycle.verification_id,registry=agent.registry)
    assert task.verification_cycles[-1].result == "improved"
    assert counts["dns_lookup"] == sum(counts.values()) == 1
    after=task.evidence[-1]
    assert after.purpose == "verification" and after.verification_id == cycle.verification_id
    assert after.tool_signature in task.executed_tool_signatures
    store.verification(sid,owner,action="start",cycle_id=cycle.verification_id,registry=agent.registry)
    assert sum(counts.values()) == 1


def test_verification_process_failure_is_not_unchanged(monkeypatch):
    agent,_,_,_,_,_,task=host_cycle()
    def fail(*a,**kw):raise RuntimeError("private")
    monkeypatch.setattr(agent.registry,"execute",fail)
    host_refresh(task,task.verification_cycles[-1],agent.registry)
    assert task.verification_cycles[-1].status == "failed" and task.verification_cycles[-1].result == "unknown"


def test_cycle_cap_and_new_baseline_uses_latest_after():
    from client_snapshot_helpers import payload,import_snapshot
    from netpilot.remediation.models import StepFeedback
    _,store,sid,owner,_,_,_=waiting_cycle()
    store.verification_max_cycles=1
    task,_,_=import_snapshot(store,sid,owner,payload("dns_failure"))
    latest_ids=set(task.verification_cycles[-1].after.evidence_ids)
    task,_=store.verification(sid,owner,action="create",reverify=True)
    assert len(task.verification_cycles) == 1 and task.verification_cycles[-1].verification_sequence == 2
    assert set(task.verification_cycles[-1].baseline.evidence_ids).issubset(latest_ids)


def test_failed_step_and_skip_do_not_activate_or_fake_improvement():
    from verification_helpers import remote_cycle
    from netpilot.remediation.models import StepFeedback
    _,store,sid,owner,_,_,task=remote_cycle()
    task,_=store.remediation(sid,owner,step_id=task.remediation_plan.steps[0].step_id,feedback=StepFeedback(session_id=sid,action="skip"))
    task,_=store.remediation(sid,owner,step_id=task.remediation_plan.steps[1].step_id,feedback=StepFeedback(session_id=sid,action="fail"))
    assert task.task_version == 1 and task.verification_cycles[-1].result == "unknown"


def test_trace_disabled_retains_no_verification_events():
    from verification_helpers import remote_cycle
    from client_snapshot_helpers import payload,import_snapshot
    from netpilot.remediation.models import StepFeedback
    _,store,sid,owner,_,_,_=remote_cycle()
    # Use a fresh session with tracing disabled, not an old trace-bearing one.
    store.reasoning_trace_enabled=False
    sid=store.create(owner).session_id
    task,_,_=import_snapshot(store,sid,owner,payload("dns_failure"))
    task,events=store.remediation(sid,owner,generate=True)
    assert not events and not task.reasoning_trace
    task,events=store.remediation(sid,owner,step_id=task.remediation_plan.steps[0].step_id,feedback=StepFeedback(session_id=sid,action="complete"))
    task,_,events=import_snapshot(store,sid,owner,payload())
    assert not events and not task.reasoning_trace and task.verification_cycles[-1].result == "improved"
