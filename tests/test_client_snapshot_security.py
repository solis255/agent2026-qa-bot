import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user
from target_helpers import local_app
from client_snapshot_helpers import payload, encoded, upload
from netpilot.client_snapshot.validation import parse_snapshot, SnapshotValidationError


@pytest.mark.parametrize("key", ["mac", "MAC_Address", "bssid", "ssid", "password", "cookie", "authorization", "api_key", "token", "secret", "credential", "GUID", "pnp_device_id", "serial_number"])
def test_cs08_sensitive_keys_are_rejected_everywhere(key):
    value = payload()
    value["checks"][0]["result"][key] = "do-not-persist"
    with pytest.raises(SnapshotValidationError, match="sensitive_fields"):
        parse_snapshot(encoded(value))


@pytest.mark.parametrize("raw", [b"not-json", b'{"schema_version":1,"schema_version":1}', b'{"schema_version":NaN}', b"[" * 10000 + b"]" * 10000])
def test_cs10_bad_json_is_safe(raw):
    with pytest.raises(SnapshotValidationError):
        parse_snapshot(raw)


def test_depth_strings_credentials_and_extra_forbid():
    with pytest.raises(SnapshotValidationError, match="invalid_json"):
        parse_snapshot(b"1" * 5000)
    cases = []
    value = payload(); value["client"]["hostname"] = "x" * 1025; cases.append(value)
    value = payload(); value["proxy"]["winhttp_proxy"] = "http://user:password@proxy:8080"; cases.append(value)
    value = payload(); value["checks"][0]["result"]["raw_error"] = "arbitrary text"; cases.append(value)
    value = payload(); value["extra"] = {}; cursor = value["extra"]
    for _ in range(20):
        cursor["nested"] = {}; cursor = cursor["nested"]
    cases.append(value)
    for value in cases:
        with pytest.raises(SnapshotValidationError):
            parse_snapshot(encoded(value))


def test_cs09_cs11_size_streaming_and_error_privacy(tmp_path):
    app, _ = local_app(tmp_path)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        assert upload(client, sid, b" " * 262145).status_code == 413
        value = payload(); value["secret"] = "sensitive-test-value"
        response = upload(client, sid, value)
        assert response.status_code == 422
        assert "sensitive-test-value" not in response.text
        # Explicit chunked body: no Content-Length to rely on.
        boundary = "snapshot-boundary"
        def chunks():
            yield f'--{boundary}\r\nContent-Disposition: form-data; name="session_id"\r\n\r\n{sid}\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="x.json"\r\n\r\n'.encode()
            for _ in range(300):
                yield b"x" * 1024
            yield f"\r\n--{boundary}--\r\n".encode()
        response = client.post("/api/session/client-snapshot",content=chunks(),headers={"Content-Type":f"multipart/form-data; boundary={boundary}"})
        assert response.status_code == 413
        assert app.state.diagnosis_repository.count(owner) == 0
