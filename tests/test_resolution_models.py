from uuid import uuid4
import pytest
from pydantic import ValidationError
from netpilot.resolution.models import ResolutionRecord,ConfirmationRequest,ResolutionRequest
from netpilot.config import Settings


@pytest.mark.parametrize("state",["diagnosing","action_required","verifying","resolved","improved","unresolved","escalated"])
def test_only_seven_states_roundtrip(state):
    record=ResolutionRecord(state=state)
    assert ResolutionRecord.model_validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize("state",["fixed","done","failed","closed","success"])
def test_no_synonym_states(state):
    with pytest.raises(ValidationError):ResolutionRecord(state=state)


@pytest.mark.parametrize("extra",["state","user_id","admin_required","objective_result","reason_code"])
def test_confirmation_is_not_a_state_patch(extra):
    with pytest.raises(ValidationError):ConfirmationRequest(session_id=uuid4(),status="resolved",**{extra:"private"})


@pytest.mark.parametrize("changes",[{"resolution_max_transitions":0},{"resolution_max_transitions":201},{"resolution_escalate_after_no_improvement":0},{"resolution_escalate_after_no_improvement":21}])
def test_bounded_settings(changes):
    with pytest.raises(ValidationError):Settings(_env_file=None,**changes)
