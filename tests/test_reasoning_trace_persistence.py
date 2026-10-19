import json
import sqlite3
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from netpilot.agent import SessionStore
from netpilot.api.presenters import present_chat
from netpilot.history import SQLiteDiagnosisRepository
from reasoning_helpers import CASE_A, CASE_B, CASE_C, make_agent, run_session, trace_app


def register(client, name):
    response = client.post("/api/auth/register", json={"username":name, "password":"trace-test-password-123"})
    assert response.status_code == 201
    return UUID(response.json()["id"])


def test_rt10_three_turn_trace_reopens_from_sqlite_with_full_conversation(tmp_path):
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        owner = register(client, "trace_alice")
        sid = client.post("/api/session").json()["session_id"]
        first = client.post("/api/chat", json={"session_id":sid, "message":CASE_A}).json()
        stream = client.post("/api/chat/stream", json={"session_id":sid, "message":CASE_B})
        block = next(block for block in stream.text.split("\n\n") if "event: complete" in block)
        second = json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))["response"]
        third = client.post("/api/chat", json={"session_id":sid, "message":CASE_C}).json()
        assert first["record_id"] == second["record_id"] == third["record_id"]
        assert {step["turn_index"] for step in third["reasoning_trace"]} == {3}
        assert third["metrics"]["reasoning_trace_steps"] == len(third["reasoning_trace"])
        expected_count = sum(len(response["reasoning_trace"]) for response in (first, second, third))
        rid = UUID(first["record_id"])
    reopened = SQLiteDiagnosisRepository(tmp_path / "trace.db")
    record = reopened.get(owner, rid)
    assert len(record.reasoning_trace) == expected_count
    assert len(record.conversation_turns) == record.turn_count == 3
    assert {step.turn_index for step in record.reasoning_trace} == {1, 2, 3}
    assert record.metrics.reasoning_trace_steps == expected_count
    assert record.schema_version == 9
    with sqlite3.connect(reopened.path) as connection:
        assert connection.execute("SELECT value FROM netpilot_metadata WHERE key='schema_version'").fetchone()[0] == "3"


def test_rt11_ownership_protects_trace_history_report_export_and_session(tmp_path):
    app = trace_app(tmp_path)
    with TestClient(app) as alice, TestClient(app) as bob:
        register(alice, "trace_alice")
        sid = alice.post("/api/session").json()["session_id"]
        result = alice.post("/api/chat", json={"session_id":sid, "message":CASE_A}).json()
        assert result["reasoning_trace"]
        register(bob, "trace_bob")
        assert bob.get("/api/diagnoses").json()["items"] == []
        for suffix in ("", "/report", "/export?format=json", "/export?format=markdown"):
            assert bob.get(f"/api/diagnoses/{result['record_id']}{suffix}").status_code == 404
        assert bob.post("/api/chat", json={"session_id":sid, "message":CASE_B}).status_code == 404


def test_legacy_v3_defaults_to_empty_trace_without_reconstruction(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "legacy.db")
    owner = uuid4()
    response = present_chat(uuid4(), make_agent().run(CASE_A))
    record = repository.upsert_session(owner, CASE_A, response)
    payload = record.model_dump(mode="json", exclude={"reasoning_trace"})
    payload["schema_version"] = 3
    for key in list(payload["metrics"]):
        if key.startswith("reasoning_"):
            del payload["metrics"][key]
    with sqlite3.connect(repository.path) as connection:
        connection.execute("UPDATE diagnosis_records SET schema_version=3, snapshot_json=? WHERE record_id=?", (json.dumps(payload), str(record.record_id)))
    loaded = SQLiteDiagnosisRepository(repository.path).get(owner, record.record_id)
    assert loaded.reasoning_trace == []
    assert loaded.metrics.reasoning_trace_steps == 0
    assert loaded.conversation_turns == record.conversation_turns


def test_state_change_preserves_trace_and_distinct_observations_despite_transport_ids(tmp_path):
    sessions, agent = SessionStore(), make_agent()
    owner = uuid4()
    sid = sessions.create(owner).session_id
    repo = SQLiteDiagnosisRepository(tmp_path / "state.db")
    for question in (CASE_A, "我重新连接网络后，请完整排查网页打不开的问题。"):
        result = run_session(agent, sessions, sid, owner, question)
        record = repo.upsert_session(owner, question, present_chat(sid, result))
    assert {step.task_version for step in record.reasoning_trace} == {1, 2}
    known = {tool.evidence_id for tool in record.tool_calls}
    assert len(known) == 10
    assert all(identifier in known for step in record.reasoning_trace for identifier in step.evidence_ids)


def test_session_history_cap_is_shared_and_no_extra_trace_appears(tmp_path):
    limit = 12
    sessions = SessionStore(reasoning_trace_max_steps=limit)
    agent = make_agent(reasoning_trace_max_steps=limit)
    owner = uuid4()
    sid = sessions.create(owner).session_id
    repository = SQLiteDiagnosisRepository(tmp_path / "bounded.db", reasoning_trace_max_steps=limit)
    for question in (CASE_A, *([CASE_B] * 15)):
        result = run_session(agent, sessions, sid, owner, question)
        record = repository.upsert_session(owner, question, present_chat(sid, result))
    assert len(sessions.task_state(sid, owner).reasoning_trace) <= limit
    assert len(repository.get(owner, record.record_id).reasoning_trace) <= limit
    assert record.metrics.reasoning_trace_steps == len(record.reasoning_trace)
    assert len(record.conversation_turns) == 16


def test_history_analysis_trace_counts_only_current_user_records(tmp_path):
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        register(client, "trace_history")
        for _ in range(3):
            sid = client.post("/api/session").json()["session_id"]
            assert client.post("/api/chat", json={"session_id":sid, "message":CASE_A}).status_code == 200
        sid = client.post("/api/session").json()["session_id"]
        result = client.post("/api/chat", json={"session_id":sid, "message":"根据我今天三次诊断记录进行比较。"}).json()
        assert result["metrics"]["turn_intent"] == "history_analysis"
        assert result["metrics"]["network_tool_calls"] == 0
        assert result["metrics"]["history_context_records"] == 3
        assert any("3 条" in step["summary"] for step in result["reasoning_trace"] if step["phase"] == "evidence")
