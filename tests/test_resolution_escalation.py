import pytest
from resolution_helpers import finished,evaluate,exhaust
from client_snapshot_helpers import payload,import_snapshot
from netpilot.agent.hypotheses import Hypothesis
from netpilot.resolution.policy import EscalationPolicy


def test_rs08_two_valid_unchanged_and_exhausted_steps():
    _,store,sid,owner,_,_,_=finished("dns_failure")
    task,_=store.verification(sid,owner,action="create",reverify=True)
    cycle=task.verification_cycles[-1]
    store.verification(sid,owner,action="start",cycle_id=cycle.verification_id)
    task,_,_=import_snapshot(store,sid,owner,payload("dns_failure"));exhaust(task)
    result=evaluate(task)
    assert result.state == "escalated" and result.escalation_reason == "repeated_no_improvement"
    assert "2 轮" in result.escalation_summary


@pytest.mark.parametrize("excluded",["inconclusive","failed","superseded"])
def test_invalid_cycles_do_not_count(excluded):
    *_,task=finished("dns_failure");cycle=task.verification_cycles[-1]
    other=cycle.model_copy(deep=True);other.status=excluded
    decision=EscalationPolicy(2).evaluate(plan=exhaust(task).remediation_plan,cycles=[cycle,other])
    assert decision.reason_code != "repeated_no_improvement"


def test_improvement_breaks_streak_and_threshold_configurable():
    *_,task=finished("dns_failure");cycle=task.verification_cycles[-1]
    better=cycle.model_copy(update={"result":"improved"})
    assert EscalationPolicy(2).evaluate(plan=exhaust(task).remediation_plan,cycles=[cycle,better,cycle]).reason_code != "repeated_no_improvement"
    assert EscalationPolicy(1).evaluate(plan=task.remediation_plan,cycles=[cycle]).reason_code == "repeated_no_improvement"


def test_rs09_multiple_supported_infrastructure_evidence_required():
    *_,task=finished("dns_failure");exhaust(task)
    records=[r for r in task.reusable_evidence() if r.status == "abnormal"]
    hypothesis=Hypothesis(name="infrastructure_issue",status="supported",supporting_evidence_ids=[r.evidence_id for r in records])
    policy=EscalationPolicy()
    result=policy.evaluate(plan=task.remediation_plan,cycles=[],hypotheses=[hypothesis],evidence=records)
    assert result.reason_code == "infrastructure_suspected" and "不等于已确认" in result.summary
    hypothesis.supporting_evidence_ids=records[:1] and [records[0].evidence_id]
    assert policy.evaluate(plan=task.remediation_plan,cycles=[],hypotheses=[hypothesis],evidence=records).reason_code != "infrastructure_suspected"


def test_skipped_and_failed_not_claimed_ineffective():
    *_,task=finished("dns_failure");exhaust(task,"skipped")
    result=evaluate(task)
    assert result.state == "escalated" and result.escalation_reason == "user_declined_remaining_steps"
    assert "跳过不表示措施无效" in result.escalation_summary
    exhaust(task,"failed")
    assert evaluate(task).escalation_reason != "repeated_no_improvement"


@pytest.mark.parametrize("change,reason",[({"requires_admin":True},"admin_required"),({"risk":"high"},"no_safe_remediation_left")])
def test_admin_and_risk_boundaries_are_recommendations_only(change,reason):
    *_,task=finished();exhaust(task)
    task.remediation_plan.status="in_progress"
    task.remediation_plan.steps[0]=task.remediation_plan.steps[0].model_copy(update={"status":"pending",**change})
    decision=EscalationPolicy().evaluate(plan=task.remediation_plan,cycles=[])
    assert decision.recommended and decision.reason_code == reason


def test_no_observability_recommendation_is_not_infrastructure_claim():
    *_,task=finished();exhaust(task)
    result=EscalationPolicy().evaluate(plan=task.remediation_plan,cycles=[],insufficient_observability=True)
    assert result.reason_code == "insufficient_observability" and "不把采集失败" in result.summary


def test_new_case_epoch_does_not_count_previous_attempts():
    *_,task=finished("dns_failure");exhaust(task)
    task.resolution.case_start_task_version=task.task_version
    assert evaluate(task,threshold=1).escalation_reason != "repeated_no_improvement"
