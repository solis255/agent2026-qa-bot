import pytest
from pydantic import ValidationError
from escalation_helpers import case
from netpilot.escalation.models import EscalationPackage,EscalationPrivacyPolicy,PackageRequest
from netpilot.escalation.builder import build_package,package_digest


def test_ep21_deep_immutable_exact_schema_and_digest():
    p=build_package(case())
    assert EscalationPackage.model_validate_json(p.model_dump_json()) == p
    assert p.package_digest == package_digest(p)
    for obj,key,value in [(p,"package_version",2),(p.target,"subject","unknown"),(p.evidence_summary[0],"summary","changed")]:
        with pytest.raises(ValidationError):setattr(obj,key,value)
    assert isinstance(p.evidence_summary,tuple) and isinstance(p.verification_summary[0].key_diffs,tuple)


@pytest.mark.parametrize("field",["redact_mac","redact_hostname","redact_ssid","redact_tokens","redact_cookies"])
def test_mandatory_redaction_cannot_be_disabled(field):
    with pytest.raises(ValidationError):EscalationPrivacyPolicy(**{field:False})


def test_clients_cannot_inject_server_state():
    task=case()
    with pytest.raises(ValidationError):PackageRequest(session_id=task.session_id,resolution={"state":"escalated"})
