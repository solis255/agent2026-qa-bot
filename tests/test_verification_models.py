from uuid import uuid4
import pytest
from pydantic import ValidationError
from verification_helpers import remote_cycle
from netpilot.verification.models import ObservationRequest, VerificationRequest, UserVerificationObservation


def test_models_roundtrip_baseline_and_baseline_values_are_frozen():
    *_,task=remote_cycle();cycle=task.verification_cycles[-1]
    assert cycle.model_validate_json(cycle.model_dump_json()) == cycle
    with pytest.raises(ValidationError):cycle.baseline=cycle.baseline.model_copy()
    with pytest.raises(ValidationError):cycle.baseline.evidence_ids=()
    with pytest.raises(ValidationError):cycle.checks[0].baseline_value="tampered"
    assert isinstance(cycle.baseline.evidence_ids,tuple)


@pytest.mark.parametrize("extra",["command","user_id","tool_args","risk_override"])
def test_request_rejects_external_execution_authority(extra):
    with pytest.raises(ValidationError):VerificationRequest(session_id=uuid4(),**{extra:"private"})


@pytest.mark.parametrize("note",["密码：secret","api_key=secret","Bearer private","a"*501])
def test_observation_privacy_and_length(note):
    with pytest.raises(ValidationError):ObservationRequest(session_id=uuid4(),symptom_status="unknown",note=note)


def test_subjective_resolved_is_not_resolution_state():
    observation=UserVerificationObservation(symptom_status="resolved_by_user_report",note="我感觉好了")
    assert observation.symptom_status == "resolved_by_user_report"
