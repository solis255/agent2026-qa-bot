import pytest
from pydantic import ValidationError
from remediation_helpers import task_with_snapshot, build
from netpilot.remediation.models import RemediationPlan,RemediationStep,StepFeedback


def test_model_roundtrip_and_legacy_absence():
    *_,task=task_with_snapshot()
    plan=build(task)
    assert RemediationPlan.model_validate_json(plan.model_dump_json()) == plan
    assert all(step.created_at.tzinfo and step.updated_at.tzinfo for step in plan.steps)


@pytest.mark.parametrize("updates",[{"risk":"extreme"},{"instructions":[]},{"verification":""},{"order":0},{"changes_system_state":True,"rollback_instructions":[]},{"status":"skipped","outcome":"improved"},{"command":"bad"}])
def test_step_invariants(updates):
    *_,task=task_with_snapshot()
    value=build(task).steps[0].model_dump()
    value.update(updates)
    with pytest.raises(ValidationError):RemediationStep.model_validate(value)


def test_status_is_not_resolution_and_skipped_not_executed():
    *_,task=task_with_snapshot()
    plan=build(task)
    assert "resolved" not in type(plan).model_fields
    with pytest.raises(ValidationError):StepFeedback(session_id=task.session_id,action="skip",outcome="improved")
    with pytest.raises(ValidationError):StepFeedback(session_id=task.session_id,action="complete",risk_override="high")
