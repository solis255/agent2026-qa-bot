from datetime import timedelta
import pytest
from resolution_helpers import finished,evaluate,exhaust
from verification_helpers import remote_cycle,waiting_cycle
from netpilot.verification.models import UserVerificationObservation
from netpilot.verification.evaluator import VerificationEvaluator


def test_rs01_rs02_rs03_initial_plan_and_waiting():
    from target_helpers import local_session
    _,store,sid,owner,_,_=local_session()
    assert store.task_state(sid,owner).resolution.state == "diagnosing"
    *_,task=remote_cycle()
    assert task.resolution.state == "action_required"
    *_,task=waiting_cycle()
    assert task.resolution.state == "verifying"


def test_rs04_strict_recovered_and_user_confirmed():
    *_,task=finished()
    assert evaluate(task,"resolved").state == "resolved"
    assert evaluate(task,"resolved").objective_result == "improved"


def test_rs05_conflicting_verification_retains_objective_improvement():
    *_,task=finished();cycle=task.verification_cycles[-1]
    cycle.user_observation=UserVerificationObservation(symptom_status="unchanged_by_user_report")
    cycle.result,cycle.result_summary=VerificationEvaluator().evaluate(cycle);cycle.status="inconclusive"
    result=evaluate(task,"not_resolved")
    assert cycle.result == "inconclusive" and result.state == "improved" and result.objective_result == "improved"
    assert "仍报告" in result.reason_summary
    assert evaluate(task,"resolved").state != "resolved"  # unresolved 12E conflict cannot be ignored


def test_rs06_subjective_only_does_not_resolve():
    from target_helpers import local_session
    _,store,sid,owner,_,_=local_session();task=store.task_state(sid,owner)
    result=evaluate(task,"resolved")
    assert result.state == "improved" and result.objective_result == "unknown" and "缺少" in result.reason_summary


def test_rs07_rs11_rs12_plan_and_improvement_not_resolution():
    *_,task=finished()
    assert evaluate(task).state == "improved"
    *_,task=finished("dns_failure");exhaust(task)
    assert evaluate(task).state == "unresolved"
    assert task.remediation_plan.status == "completed" and evaluate(task,"resolved").state != "resolved"


@pytest.mark.parametrize("problem",["stale","skew","expired","missing","superseded","other_target","other_task","host_spoof"])
def test_rs14_invalid_after_never_resolved(problem):
    *_,task=finished();cycle=task.verification_cycles[-1]
    record=next(r for r in task.evidence if r.evidence_id in cycle.after.evidence_ids)
    if problem == "stale":record.stale=True
    if problem == "skew":record.clock_skew_suspected=True
    if problem == "expired":record.expires_at=record.observed_at-timedelta(seconds=1)
    if problem == "missing":task.evidence=[r for r in task.evidence if r.evidence_id != record.evidence_id]
    if problem == "superseded":record.superseded=True
    if problem == "other_target":record.target_version+=1
    if problem == "other_task":record.task_version+=1
    if problem == "host_spoof":record.execution_scope="execution_host";record.evidence_origin="tool";record.execution_context="netpilot_host"
    assert evaluate(task,"resolved").state != "resolved"


def test_critical_partial_recovery_cannot_resolve():
    from client_snapshot_helpers import payload,import_snapshot
    _,store,sid,owner,_,_,_=waiting_cycle()
    value=payload();dns=next(c for c in value["checks"] if c["type"] == "dns");dns["status"]="abnormal";dns["result"]={"addresses":[],"error_code":"dns_query_failed"}
    task,_,_=import_snapshot(store,sid,owner,value)
    assert task.verification_cycles[-1].result == "improved" and evaluate(task,"resolved").state == "improved"


def test_rs13_worsened_never_resolved():
    *_,task=finished();cycle=task.verification_cycles[-1]
    # Controlled semantic comparator result, not an LLM answer.
    cycle.checks[0]=cycle.checks[0].model_copy(update={"baseline_status":"normal","after_status":"abnormal","change":"worsened","importance":"critical"})
    cycle.result="worsened"
    assert evaluate(task,"resolved").state != "resolved"


def test_evaluator_is_pure():
    *_,task=finished();before=task.model_dump_json()
    first=evaluate(task);second=evaluate(task)
    assert first == second and task.model_dump_json() == before


def test_forged_check_cannot_override_actual_after_evidence():
    *_,task=finished("dns_failure");cycle=task.verification_cycles[-1]
    for check in cycle.checks:
        if check.importance == "critical":
            check.after_status="normal";check.change="improved"
    cycle.result="improved"
    assert evaluate(task,"resolved").state != "resolved"


def test_old_task_plan_without_current_verification_not_actionable():
    *_,task=remote_cycle()
    task.task_version+=10;task.verification_cycles=[]
    assert evaluate(task).state == "diagnosing"


def test_host_after_without_expiry_has_bounded_resolution_freshness():
    from verification_helpers import host_cycle
    agent,store,sid,owner,_,_,task=host_cycle()
    task,_=store.verification(sid,owner,action="start",cycle_id=task.verification_cycles[-1].verification_id,registry=agent.registry)
    cycle=task.verification_cycles[-1]
    cycle=cycle.model_copy(update={"baseline":cycle.baseline.model_copy(update={"captured_at":cycle.baseline.captured_at-timedelta(minutes=16)})})
    task.verification_cycles[-1]=cycle
    for r in task.evidence:r.observed_at-=timedelta(minutes=16)
    assert evaluate(task,"resolved").state != "resolved"
