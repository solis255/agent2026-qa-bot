import pytest
from netpilot.privacy import PrivacyPolicy, redact_text


@pytest.mark.parametrize("value,removed", [
    ("password=test123", "test123"), ("password: abc", "abc"),
    ("Authorization: Bearer abc.def", "abc.def"), ("Basic dXNlcjpwdw==", "dXNlcjpwdw=="),
    ("Cookie: sid=12345; other=cookie-two", "cookie-two"), ("Set-Cookie: sid=12345", "12345"),
    ("token=abc", "abc"), ("api_key=abc", "abc"),
    ("00:11:22:33:44:55", "00:11:22:33:44:55"), ("00-11-22-33-44-55", "00-11-22-33-44-55"),
    ("0011.2233.4455", "0011.2233.4455"), ("DESKTOP-ABC", "DESKTOP-ABC"),
    ("SSID=TJU-WLAN", "TJU-WLAN"), ("hostname=office-box", "office-box"),
    ("-----BEGIN PRIVATE KEY-----\nopaque-key-material\n-----END PRIVATE KEY-----", "opaque-key-material"),
])
def test_free_text_detection_and_idempotency(value, removed):
    result = redact_text(value)
    assert removed not in result.value
    assert redact_text(result.value).value == result.value


def test_false_positives_and_optional_contact_redaction():
    text = "token bucket algorithm session_id=business-resource port 443 DNS 172.23.0.1 github.com www.tju.edu.cn"
    assert redact_text(text).value == text
    text = "a@example.com 13812345678"
    assert redact_text(text).value == text
    assert "example.com" not in redact_text(text, PrivacyPolicy(redact_email=True, redact_phone=True)).value


def test_redact_before_truncate_and_key_block_without_end():
    text = "x" * 55 + " password=LONG-SECRET-AT-BOUNDARY" + "x" * 100
    result = redact_text(text, PrivacyPolicy(max_free_text_length=64))
    assert "LONG-SECRET" not in result.value and len(result.value) <= 64
    assert "credential" in result.redacted_categories
    assert redact_text(result.value, PrivacyPolicy(max_free_text_length=64)).value == result.value
    assert "key-material" not in redact_text("-----BEGIN RSA PRIVATE KEY-----\nkey-material").value


def test_truncation_never_creates_non_idempotent_partial_url_or_placeholder():
    policy = PrivacyPolicy(max_free_text_length=64)
    for offset in range(65):
        for tail in ["password=opaque", "https://example.com/?text=" + "%E4%B8%AD" * 20]:
            first = redact_text("x" * offset + " " + tail, policy).value
            assert len(first) <= 64
            assert redact_text(first, policy).value == first
