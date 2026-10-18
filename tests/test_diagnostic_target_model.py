import pytest
from pydantic import ValidationError
from netpilot.diagnostic_target import DiagnosticTarget, legacy_target


def test_target_default_and_legacy_are_unknown_without_inference():
    target = DiagnosticTarget()
    assert target.subject == target.relationship_to_netpilot == "unknown"
    assert target.execution_context == "unavailable"
    assert target.limitation_code == "unknown_target"
    assert target.target_version == 1
    assert target.updated_at.tzinfo is not None
    assert legacy_target() == legacy_target()


@pytest.mark.parametrize("values", [{"subject":"browser"},{"execution_context":"user_client"},{"target_version":0},{"target_version":True},{"local_tools_applicable":True},{"source":"browser"}])
def test_target_model_rejects_unknown_fields_or_invalid_types(values):
    with pytest.raises(ValidationError):
        DiagnosticTarget(**values)
