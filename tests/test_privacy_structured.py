import json
import pytest
from pydantic import BaseModel

from netpilot.privacy import PrivacyPolicy, redact_mapping, redact_model, redact_sequence


@pytest.mark.parametrize("key", ["password", "passwd", "pwd", "cookie", "Set-Cookie", "Authorization", "auth_token", "token", "access_token", "refresh_token", "api_key", "apikey", "secret", "client_secret", "credential", "credentials", "session_token", "private_key", "X-API-Key", "accessToken"])
def test_nested_sensitive_keys(key):
    value = {"nested": [{key: "UNIQUE-CREDENTIAL", "dns_server": "172.23.1.1"}], "session_id": "internal-resource-id"}
    result = redact_mapping(value)
    assert "UNIQUE-CREDENTIAL" not in json.dumps(result.value)
    assert result.value["nested"][0]["dns_server"] == "172.23.1.1"
    assert result.value["session_id"] == value["session_id"]
    assert result.redacted_categories == ["credential"]
    assert result.redacted_count == 1
    assert value["nested"][0][key] == "UNIQUE-CREDENTIAL"


def test_known_identifiers_removed_everywhere_and_idempotent():
    value = {"hostname": "office-device-42", "ssid": "unusual-wlan", "summary": "office-device-42 on unusual-wlan"}
    result = redact_mapping(value)
    assert "office-device-42" not in str(result.value) and "unusual-wlan" not in str(result.value)
    again = redact_mapping(result.value)
    assert again.value == result.value and not again.changed


def test_models_sequences_depth_and_safe_metadata():
    class Sample(BaseModel):
        summary: str
        password: str
    result = redact_model(Sample(summary="token=abc", password="pw"))
    assert isinstance(result.value, Sample)
    assert result.value.password == "[REDACTED]"
    assert redact_sequence(["token=abc"]).value == ["token=[REDACTED]"]
    assert "deep-secret" not in str(redact_mapping({"x": {"x": {"x": "deep-secret"}}}, PrivacyPolicy(max_depth=1)).value)
    assert "depth_limit" in redact_mapping({"x": {"x": {"x": "deep-secret"}}}, PrivacyPolicy(max_depth=1)).warnings


def test_configurable_identity_and_no_network_name_false_positive():
    value = {"hostname": "ordinary-device", "network_name": "campus", "ssid": "wireless-id"}
    result = redact_mapping(value, PrivacyPolicy(redact_hostname=False))
    assert result.value["hostname"] == "ordinary-device"
    assert result.value["network_name"] == "campus"
    assert result.value["ssid"] == "[REDACTED_SSID]"


def test_redaction_expansion_respects_model_field_limit():
    from pydantic import Field
    class Note(BaseModel):
        note: str = Field(max_length=80)
    original = Note(note=("token=x " * 10).strip())
    safe = redact_model(original).value
    assert len(safe.note) <= 80
    assert Note.model_validate_json(safe.model_dump_json()) == safe
    assert redact_model(safe).value == safe


def test_known_secret_does_not_rewrite_schema_keys():
    safe = redact_mapping({"token": "dns", "dns_server": "172.23.0.1", "session_id": "owned"}).value
    assert safe == {"token": "[REDACTED]", "dns_server": "172.23.0.1", "session_id": "owned"}
