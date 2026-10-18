from uuid import UUID
from fastapi.testclient import TestClient
from conftest import register_test_user
from target_helpers import local_app
from client_snapshot_helpers import payload, upload


def test_cs01_cs13_upload_dedup_and_session_refresh(tmp_path):
    app, counts = local_app(tmp_path)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        value = payload()
        response = upload(client, sid, value)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["diagnostic_target"]["subject"] == "user_client"
        assert body["diagnostic_target"]["relationship_to_netpilot"] == "remote"
        assert body["diagnostic_target"]["target_version"] == 1
        assert body["client_snapshot_summary"]["evidence_count"] == 5
        again = upload(client, sid, value).json()
        assert again["duplicate"] and again["reasoning_trace"] == []
        assert again["client_snapshot_summary"] == body["client_snapshot_summary"]
        assert len(again["client_evidence"]) == 5
        restored = client.get(f"/api/session/{sid}").json()
        assert restored["client_snapshot_summary"] == body["client_snapshot_summary"]
        state = app.state.sessions.task_state(UUID(sid), owner)
        assert state.turn_index == 0 and state.snapshot_sequence == 1
        assert app.state.diagnosis_repository.count(owner) == 0
        assert sum(counts.values()) == 0


def test_cs14_owner_auth_and_busy_boundaries(tmp_path):
    app, _ = local_app(tmp_path)
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as anon:
        owner = register_test_user(alice)
        sid = alice.post("/api/session").json()["session_id"]
        register_test_user(bob)
        assert upload(anon, sid, payload()).status_code == 401
        assert upload(bob, sid, payload()).status_code == 404
        app.state.sessions.begin_turn(UUID(sid), owner)
        assert upload(alice, sid, payload()).status_code == 409
        app.state.sessions.abort_turn(UUID(sid))


def test_extension_mime_and_single_file_contract(tmp_path):
    app, _ = local_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        assert upload(client, sid, payload(), filename="script.ps1").status_code == 415
        assert upload(client, sid, payload(), mime="application/octet-stream").status_code == 200
        assert client.post("/api/session/client-snapshot", data={"session_id":sid}, files=[("file",("a.json",b"{}")),("file",("b.json",b"{}"))]).status_code == 422
        assert client.post("/api/session/client-snapshot",json={"session_id":sid}).status_code == 415
        assert upload(client, sid, payload(), headers={"Origin":"https://evil.example"}).status_code == 403
        assert upload(client, sid, payload(), headers={"Origin":"http://["}).status_code == 403
        assert client.post("/api/session/client-snapshot", content=b"not-a-multipart-body", headers={"Content-Type":"multipart/form-data; boundary=expected"}).status_code == 422


def test_storage_failure_rolls_back_import(tmp_path, monkeypatch):
    from netpilot.history import DiagnosisStorageError
    app, _ = local_app(tmp_path)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        def fail(*args):
            raise DiagnosisStorageError("controlled")
        monkeypatch.setattr(app.state.diagnosis_repository, "update_client_snapshot", fail)
        assert upload(client, sid, payload()).status_code == 503
        task = app.state.sessions.task_state(UUID(sid), owner)
        assert task.snapshot_sequence == 0 and not task.evidence
