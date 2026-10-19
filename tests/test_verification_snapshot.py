from datetime import timedelta
import pytest
from verification_helpers import waiting_cycle
from client_snapshot_helpers import payload,import_snapshot
from netpilot.client_snapshot.validation import SnapshotValidationError


@pytest.mark.parametrize("name,expected",[("valid","improved"),("dns_failure","unchanged")])
def test_bv01_bv02_remote_snapshot_diff(name,expected):
    _,store,sid,owner,counts,_,before=waiting_cycle()
    task,_,events=import_snapshot(store,sid,owner,payload(name))
    cycle=task.verification_cycles[-1]
    assert cycle.result == expected and cycle.status == "completed"
    assert cycle.after.task_version == 2 and cycle.baseline.task_version == 1
    assert any(e.title == "完成修复前后对比" for e in events)
    assert sum(counts.values()) == 0


def test_bv08_old_after_waits_and_invalid_upload_does_not_change():
    _,store,sid,owner,_,_,task=waiting_cycle();cycle=task.verification_cycles[-1]
    value=payload();value["generated_at"]=(cycle.baseline.captured_at-timedelta(seconds=1)).isoformat()
    task,_,_=import_snapshot(store,sid,owner,value)
    assert task.verification_cycles[-1].status == "awaiting_after_evidence"
    assert "不晚于" in task.verification_cycles[-1].result_summary
    value["schema_version"]=99
    with pytest.raises(SnapshotValidationError):import_snapshot(store,sid,owner,value)
    assert store.task_state(sid,owner).verification_cycles[-1].status == "awaiting_after_evidence"


@pytest.mark.parametrize("minutes",[-30,10])
def test_stale_and_future_after_never_improved(minutes):
    _,store,sid,owner,_,_,task=waiting_cycle()
    # Old baseline permits an old-but-newer After to exercise stale binding.
    current=store._sessions[sid].task_state
    cycle=current.verification_cycles[-1]
    if minutes < 0:
        frozen=cycle.baseline.model_copy(update={"captured_at":cycle.baseline.captured_at-timedelta(hours=1)})
        current.verification_cycles[-1]=cycle.model_copy(update={"baseline":frozen})
    value=payload();value["generated_at"]=(task.verification_cycles[-1].created_at+timedelta(minutes=minutes)).isoformat()
    task,_,_=import_snapshot(store,sid,owner,value)
    cycle=task.verification_cycles[-1]
    assert cycle.result == "inconclusive" and cycle.after.stale


def test_after_wrong_task_and_scope_cannot_bind():
    from netpilot.verification.service import bind_snapshot
    *_,task=waiting_cycle()
    records=[r.model_copy(update={"observed_at":task.verification_cycles[-1].created_at+timedelta(seconds=1),"task_version":99}) for r in task.evidence]
    assert bind_snapshot(task,records) == []
    assert task.verification_cycles[-1].after is None


def test_superseded_plan_cannot_be_revived_by_after_import():
    _,store,sid,owner,_,_,_=waiting_cycle()
    store.update_environment(sid,owner,{"network_access":"off_campus"},source="user")
    task,_,_=import_snapshot(store,sid,owner,payload())
    cycle=task.verification_cycles[-1]
    assert cycle.status == "superseded" and cycle.after is None and cycle.result != "improved"
