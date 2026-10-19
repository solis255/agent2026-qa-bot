import logging
import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from target_helpers import local_app
from client_snapshot_helpers import payload, upload


@pytest.mark.parametrize("key", ["mac", "ssid", "password", "cookie", "access_token", "private_key"])
def test_forbidden_snapshot_is_rejected_with_value_free_audit(tmp_path, caplog, key):
    app, counts = local_app(tmp_path)
    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="netpilot"):
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        value = payload(); value[key] = "forbidden-original-value"
        result = upload(client, sid, value)
        assert result.status_code == 422
        assert "forbidden-original-value" not in result.text + caplog.text
        assert "sensitive_upload_rejected" in caplog.text
        assert sum(counts.values()) == 0


def test_legal_snapshot_normalized_evidence_is_safe(tmp_path):
    app, _ = local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        value = payload(); value["client"]["hostname"] = "DESKTOP-PRIVACY"
        result = upload(client, sid, value)
        assert result.status_code == 200
        assert "DESKTOP-PRIVACY" not in result.text
        body = result.json()
        assert body["client_snapshot_summary"]["privacy_policy_version"] == "1"
        assert all(e["privacy_metadata"]["applied"] for e in body["client_evidence"])
