import pytest
from verification_helpers import remote_cycle
from netpilot.verification.evaluator import VerificationEvaluator
from netpilot.verification.models import VerificationCheck,UserVerificationObservation


@pytest.mark.parametrize("changes,expected",[(["improved","unchanged"],"improved"),(["unchanged","unchanged"],"unchanged"),(["improved","worsened"],"worsened"),(["not_comparable"],"inconclusive"),([],"inconclusive"),(["unchanged","not_comparable"],"inconclusive")])
def test_critical_overall_rules(changes,expected):
    *_,task=remote_cycle();cycle=task.verification_cycles[-1]
    cycle.checks=[VerificationCheck(metric="dns_resolution",baseline_status="abnormal",change=c,importance="critical") for c in changes]
    assert VerificationEvaluator().evaluate(cycle)[0] == expected


@pytest.mark.parametrize("observation,change,status",[("resolved_by_user_report","unchanged","abnormal"),("unchanged_by_user_report","improved","normal"),("worsened_by_user_report","improved","normal")])
def test_bv09_bv10_conflict(observation,change,status):
    *_,task=remote_cycle();cycle=task.verification_cycles[-1]
    cycle.checks=[VerificationCheck(metric="dns_resolution",baseline_status="abnormal",after_status=status,change=change,importance="critical")]
    cycle.user_observation=UserVerificationObservation(symptom_status=observation)
    result,reason=VerificationEvaluator().evaluate(cycle)
    assert result == "inconclusive" and ("不一致" in reason or "差异" in reason)


def test_bv11_subjective_only_and_supporting_cannot_override():
    *_,task=remote_cycle();cycle=task.verification_cycles[-1]
    cycle.user_observation=UserVerificationObservation(symptom_status="improved_by_user_report")
    assert VerificationEvaluator().evaluate(cycle)[0] == "inconclusive"
    cycle.checks=[VerificationCheck(metric="dns_resolution",baseline_status="abnormal",change="unchanged",importance="critical"),VerificationCheck(metric="network_configuration",baseline_status="abnormal",change="improved",importance="supporting")]
    cycle.user_observation=None
    assert VerificationEvaluator().evaluate(cycle)[0] == "unchanged"
