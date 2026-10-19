import pytest
from pydantic import ValidationError

from netpilot.config import Settings
from netpilot.privacy import PrivacyPolicy, RedactionMetadata


@pytest.mark.parametrize("key", ["redact_passwords", "redact_tokens", "redact_cookies", "redact_authorization", "strip_url_credentials", "strip_sensitive_query_params"])
def test_hard_redaction_cannot_be_disabled(key):
    with pytest.raises(ValidationError):
        PrivacyPolicy(**{key: False})


def test_settings_and_default_policy(monkeypatch):
    monkeypatch.setenv("PRIVACY_MASK_PRIVATE_IP", "true")
    monkeypatch.setenv("PRIVACY_REDACT_EMAIL", "true")
    policy = PrivacyPolicy.from_settings(Settings(_env_file=None))
    assert policy.mask_private_ip and policy.redact_email
    assert not PrivacyPolicy().mask_private_ip
    assert RedactionMetadata().policy_version == "1"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, privacy_policy_version="unimplemented")
