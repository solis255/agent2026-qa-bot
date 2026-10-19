import json
import pytest
from uuid import uuid4
from privacy_helpers import response
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.reports import build_diagnosis_report, export_diagnosis_report
from netpilot.escalation.builder import build_package, package_digest
from netpilot.escalation.exports import export_package
from netpilot.privacy import PrivacyPolicy, current_policy

TEXT = "hostname=DESKTOP-ABC\nMAC=00-11-22-33-44-55\nSSID=TJU-WLAN\nAuthorization: Bearer bearer-secret\nhttps://example.com/?token=query-secret&lang=zh\nDNS 172.23.0.1 Gateway 172.23.128.1 port 443"
SECRETS = ["DESKTOP-ABC", "00-11-22-33-44-55", "TJU-WLAN", "bearer-secret", "query-secret", "note-secret"]


@pytest.mark.parametrize("format", ["markdown", "json"])
def test_report_final_pass_defends_against_mutated_legacy_fields(tmp_path, format):
    repository = SQLiteDiagnosisRepository(tmp_path / "reports.db")
    record = repository.upsert_session(uuid4(), "诊断", response())
    report = build_diagnosis_report(record)
    report.conclusion = TEXT
    report.conversation_turns[0].user_message = "token=note-secret"
    content = export_diagnosis_report(report, format).content.decode()
    assert all(secret not in content for secret in SECRETS)
    assert "lang=zh" in content and "172.23.0.1" in content and "443" in content
    if format == "json": assert json.loads(content)["privacy_policy_version"] == "1"


@pytest.mark.parametrize("format", ["md", "json"])
def test_escalation_case4_in_both_formats_with_valid_digest(format):
    from escalation_helpers import case
    task = case(); task.original_symptom = TEXT; task.remediation_symptom = TEXT
    task.remediation_plan.steps[0].user_note = "token=note-secret"
    package = build_package(task)
    assert package_digest(package) == package.package_digest
    content = export_package(package, format).content.decode()
    assert all(secret not in content for secret in SECRETS)
    assert "lang=zh" in content and "172.23.0.1" in content and "443" in content
    if format == "json":
        exported = type(package).model_validate_json(content)
        assert package_digest(exported) == exported.package_digest
        assert exported.privacy_policy_version == "1"


def test_configured_export_mask(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "mask.db")
    record = repository.upsert_session(uuid4(), "诊断", response())
    token = current_policy.set(PrivacyPolicy(mask_private_ip=True))
    try:
        content = export_diagnosis_report(build_diagnosis_report(record), "json").content.decode()
    finally:
        current_policy.reset(token)
    assert "172.23.0.xxx" in content and "172.23.0.1" not in content


def test_old_package_digest_verified_before_read_safety_pass(tmp_path):
    from escalation_helpers import case
    from netpilot.escalation.builder import digest
    from netpilot.escalation.persistence import initialize, read
    import sqlite3
    package = build_package(case())
    payload = package.model_dump(mode="json", exclude={"privacy_metadata", "privacy_policy_version", "package_digest"})
    payload["issue"]["original_symptom"] = "token=legacy-package-secret"
    payload["package_digest"] = digest(payload)
    owner = uuid4()
    with sqlite3.connect(tmp_path / "old-package.db") as connection:
        connection.row_factory = sqlite3.Row
        initialize(connection)
        connection.execute("INSERT INTO escalation_packages VALUES (?,?,?,?,?,?)", (str(package.package_id), str(owner), str(package.session_id), package.package_version, package.generated_at.isoformat(), json.dumps(payload)))
        safe = read(connection, owner, package.session_id)[0]
        assert "legacy-package-secret" not in safe.model_dump_json()
        assert package_digest(safe) == safe.package_digest
        assert "legacy-package-secret" not in export_package(safe, "json").content.decode()
        assert "legacy-package-secret" in connection.execute("SELECT package_json FROM escalation_packages").fetchone()[0]
