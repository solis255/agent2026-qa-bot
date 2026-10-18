from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import register_test_user
from netpilot.agent import AgentResult, AgentStatus, ResponseMode, TurnIntent
from netpilot.api.presenters import present_chat
from netpilot.config import Settings
from netpilot.history import DiagnosisRecordNotFoundError, SQLiteDiagnosisRepository
from netpilot.llm import TokenUsage
from netpilot.main import create_app
from netpilot.reports import build_diagnosis_report, export_diagnosis_report, DiagnosisReportTooLargeError


def _response(session, index):
    return present_chat(session, AgentResult(
        answer=f"A{index}", status=AgentStatus.COMPLETED, tool_rounds=0,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        turn_intent=TurnIntent.KNOWLEDGE_REQUEST, response_mode=ResponseMode.KNOWLEDGE,
    ))


def test_three_turn_transcript_is_ordered_persisted_and_one_row_after_restart(tmp_path):
    database = tmp_path / "conversation.db"
    repository = SQLiteDiagnosisRepository(database)
    owner, session = uuid4(), uuid4()
    records = [repository.upsert_session(owner, f"U{index}", _response(session, index))
               for index in range(1, 4)]
    reopened = SQLiteDiagnosisRepository(database)
    loaded = reopened.get(owner, records[0].record_id)
    assert len({record.record_id for record in records}) == 1
    assert reopened.count(owner) == 1
    assert loaded.turn_count == len(loaded.conversation_turns) == 3
    assert loaded.schema_version == 6
    assert loaded.conversation_complete is True
    assert [(turn.user_message, turn.assistant_answer) for turn in loaded.conversation_turns] == [
        ("U1", "A1"), ("U2", "A2"), ("U3", "A3"),
    ]
    assert [turn.turn_index for turn in loaded.conversation_turns] == [1, 2, 3]
    assert all(turn.turn_intent == "knowledge_request" for turn in loaded.conversation_turns)
    assert loaded.metrics.token_usage.total_tokens == 45
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT schema_version, snapshot_json FROM diagnosis_records").fetchone()
        assert row[0] == 6
        assert len(json.loads(row[1])["conversation_turns"]) == 3
        assert connection.execute("SELECT value FROM netpilot_metadata WHERE key='schema_version'").fetchone()[0] == "3"


def _legacy_record(repository, owner, session, count, version):
    record = None
    for index in range(1, count + 1):
        record = repository.upsert_session(owner, f"U{index}", _response(session, index))
    payload = record.model_dump(mode="json", exclude={"conversation_turns", "conversation_complete"})
    payload["schema_version"] = version
    with sqlite3.connect(repository.path) as connection:
        connection.execute("UPDATE diagnosis_records SET schema_version=?, snapshot_json=? WHERE record_id=?",
                           (version, json.dumps(payload), str(record.record_id)))
    return record


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_single_turn_is_safely_read_as_complete(tmp_path, version):
    repository = SQLiteDiagnosisRepository(tmp_path / "legacy.db")
    owner, session = uuid4(), uuid4()
    record = _legacy_record(repository, owner, session, 1, version)
    loaded = SQLiteDiagnosisRepository(repository.path).get(owner, record.record_id)
    assert loaded.conversation_complete is True
    assert loaded.conversation_turns[0].user_message == "U1"
    assert loaded.conversation_turns[0].assistant_answer == "A1"


def test_legacy_multi_turn_is_partial_and_future_append_does_not_invent_answers(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "legacy.db")
    owner, session = uuid4(), uuid4()
    record = _legacy_record(repository, owner, session, 3, 2)
    loaded = repository.get(owner, record.record_id)
    assert loaded.conversation_complete is False
    assert len(loaded.conversation_turns) == 1
    assert loaded.conversation_turns[0].turn_index == 3
    assert loaded.conversation_turns[0].user_message == "U3"
    assert loaded.conversation_turns[0].assistant_answer == "A3"
    assert loaded.user_message == "U1"
    appended = repository.upsert_session(owner, "U4", _response(session, 4))
    assert appended.record_id == record.record_id
    assert appended.turn_count == 4
    assert appended.schema_version == 6
    assert appended.conversation_complete is False
    assert [(turn.turn_index, turn.assistant_answer) for turn in appended.conversation_turns] == [(3, "A3"), (4, "A4")]
    assert repository.count(owner) == 1
    assert SQLiteDiagnosisRepository(repository.path).get(owner, record.record_id) == appended
    markdown = export_diagnosis_report(build_diagnosis_report(appended), "markdown").content.decode()
    assert "仅保留部分对话内容" in markdown


def test_report_and_export_include_full_transcript_and_keep_size_limit(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "reports.db")
    owner, session = uuid4(), uuid4()
    for index in range(1, 4):
        record = repository.upsert_session(owner, f"U{index}", _response(session, index))
    report = build_diagnosis_report(record)
    assert report.conversation_complete is True
    assert report.conversation_turns == record.conversation_turns
    markdown = export_diagnosis_report(report, "markdown").content.decode()
    transcript = markdown.split("## 会话记录", 1)[1]
    positions = [transcript.index(text) for text in ("U1", "A1", "U2", "A2", "U3", "A3")]
    assert positions == sorted(positions)
    payload = json.loads(export_diagnosis_report(report, "json").content)
    assert len(payload["conversation_turns"]) == 3
    with pytest.raises(DiagnosisReportTooLargeError):
        export_diagnosis_report(report, "markdown", max_bytes=50)


class TranscriptAgent:
    def run(self, message, *, history=(), task_state=None):
        return AgentResult(answer="A" + message[1:], status=AgentStatus.COMPLETED, tool_rounds=0)


def test_chat_and_sse_share_transcript_and_auth_ownership(tmp_path):
    app = create_app(Settings(_env_file=None, rag_enabled=False, tju_api_key="test",
                              diagnosis_history_enabled=True, diagnosis_db_path=tmp_path / "api.db"))
    app.state.agent = TranscriptAgent()
    with TestClient(app) as alice, TestClient(app) as bob:
        alice_id = register_test_user(alice)
        register_test_user(bob)
        session = alice.post("/api/session").json()["session_id"]
        first = alice.post("/api/chat", json={"session_id": session, "message": "U1"}).json()
        stream = alice.post("/api/chat/stream", json={"session_id": session, "message": "U2"})
        complete = next(block for block in stream.text.split("\n\n") if "event: complete" in block)
        second = json.loads(next(line[6:] for line in complete.splitlines() if line.startswith("data: ")))["response"]
        third = alice.post("/api/chat", json={"session_id": session, "message": "U3"}).json()
        assert first["record_id"] == second["record_id"] == third["record_id"]
        path = f"/api/diagnoses/{first['record_id']}"
        detail = alice.get(path).json()
        assert detail["turn_count"] == len(detail["conversation_turns"]) == 3
        assert [turn["assistant_answer"] for turn in detail["conversation_turns"]] == ["A1", "A2", "A3"]
        assert app.state.diagnosis_repository.count(alice_id) == 1
        for suffix in ("", "/report", "/export?format=json"):
            assert bob.get(path + suffix).status_code == 404
        assert len(alice.get(path + "/report").json()["conversation_turns"]) == 3
