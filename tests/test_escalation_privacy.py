import pytest
from escalation_helpers import case
from netpilot.escalation.builder import build_package
from netpilot.escalation.models import EscalationPrivacyPolicy
from netpilot.escalation.privacy import redact
from netpilot.escalation.exports import export_package


@pytest.mark.parametrize("text,secret",[
    ("hostname=DESKTOP-ABC","DESKTOP-ABC"),("MAC:00-11-22-33-44-55","00-11-22-33-44-55"),
    ("BSSID: aa:bb:cc:dd:ee:ff","aa:bb:cc:dd:ee:ff"),("SSID=TJU-WLAN","TJU-WLAN"),
    ("token=abc123","abc123"),("password=test","test"),("Authorization: Bearer sensitive-abc","sensitive-abc"),
    ("Cookie: session=abc123; other=else","abc123"),("api_key=secret-key","secret-key"),
    ("credential: opaque-value","opaque-value"),("密码：绝密口令","绝密口令"),
    ('{"secret":"secret-value"}',"secret-value"),("Mozilla/5.0 (Windows NT 10.0) example","Windows NT 10.0"),
    ("precise location=39.123456,117.654321","39.123456"),
])
def test_ep07_ep08_ep09_both_export_formats_remove_sensitive_strings(text,secret):
    task=case();task.remediation_symptom=text;task.original_symptom=text
    task.evidence[-1].summary=text
    task.remediation_plan.steps[0]=task.remediation_plan.steps[0].model_copy(update={"user_note":text})
    package=build_package(task)
    for format in ["md","json"]:
        content=export_package(package,format).content.decode()
        assert secret not in content


def test_known_unlabelled_identifiers_removed_and_raw_data_not_exported():
    task=case();e=task.evidence[-1]
    e.data.update(hostname="office-machine-42",ssid="TJU-WLAN",token="abc123",raw_snapshot="RAW-SNAPSHOT-SENTINEL")
    e.summary="office-machine-42 TJU-WLAN abc123"
    for format in ["md","json"]:
        text=export_package(build_package(task),format).content.decode()
        assert all(s not in text for s in ["office-machine-42","TJU-WLAN","abc123","RAW-SNAPSHOT-SENTINEL"])


def test_ep10_safe_url_query_kept_credentials_fragment_removed():
    text=redact("https://name:pw@example.com/help?token=abc123&lang=zh&access_token=hidden#secret")
    assert text=="https://example.com/help?lang=zh"


def test_ep11_private_ip_default_kept_optional_mask_and_public_not_invented():
    text="172.23.221.167 192.168.1.1 8.8.8.8 fd00::1234"
    assert "172.23.221.167" in redact(text)
    masked=redact(text,EscalationPrivacyPolicy(mask_private_ip=True))
    assert "172.23.221.xxx" in masked and "192.168.1.xxx" in masked
    assert "8.8.8.8" in masked and "fd00::1234" not in masked


def test_cookie_header_multiple_values_and_space_labelled_ssid_removed():
    text=redact("Cookie: first=cookie-one; second=cookie-two\nSSID TJU-WLAN")
    assert not any(s in text for s in ["cookie-one","cookie-two","TJU-WLAN"])
