from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from conftest import register_test_user

from netpilot.agent import (
    AgentResult,
    AgentStatus,
    AgentToolStep,
    ResponseMode,
    TurnIntent,
)
from netpilot.api.presenters import present_chat
from netpilot.config import Settings
from netpilot.history import (
    DiagnosisCursorError,
    DiagnosisRecordNotFoundError,
    DiagnosisStorageError,
    SQLiteDiagnosisRepository,
)
from netpilot.llm import TokenUsage
from netpilot.main import create_app
from netpilot.models import DiagnosisRecordView
from netpilot.rag import KnowledgeSource
from netpilot.tools.schemas import DNSLookupData, ToolResult


OWNER = uuid4()


def _agent_result(index: int = 1) -> AgentResult:
    return AgentResult(
        answer=f"问题判断：第 {index} 次 DNS 解析异常。",
        status=AgentStatus.COMPLETED,
        tool_rounds=1,
        steps=[
            AgentToolStep(
                round=1,
                tool_call_id=f"history_dns_{index}",
                tool_name="dns_lookup",
                arguments={"domain": f"host-{index}.example"},
                result=ToolResult[DNSLookupData](
                    success=True,
                    tool="dns_lookup",
                    summary="域名解析失败",
                    data=DNSLookupData(resolved=False, addresses=[]),
                    duration_ms=4,
                ),
            )
        ],
        usage=TokenUsage(
            prompt_tokens=10 + index,
            completion_tokens=5,
            total_tokens=15 + index,
        ),
        llm_duration_ms=20.5 + index,
    )


def _save(
    repository: SQLiteDiagnosisRepository,
    *,
    index: int,
    session_id: UUID | None = None,
    user_id: UUID = OWNER,
):
    resolved_session = session_id or uuid4()
    response = present_chat(resolved_session, _agent_result(index))
    return repository.save(user_id, f"第 {index} 个问题", response)


def test_sqlite_history_persists_complete_snapshot_across_instances(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history" / "netpilot.db"
    first = SQLiteDiagnosisRepository(database)
    saved = _save(first, index=1)

    reopened = SQLiteDiagnosisRepository(database)
    loaded = reopened.get(OWNER, saved.record_id)

    assert reopened.count(OWNER) == 1
    assert loaded == saved
    assert loaded.metrics.token_usage.total_tokens == 16
    assert loaded.metrics.llm_duration_ms == 21.5
    assert loaded.metrics.tool_duration_ms == 4
    assert loaded.metrics.tool_calls == 1
    assert loaded.tool_calls[0].finding_status == "abnormal"


def test_same_session_upserts_one_stable_cumulative_record(tmp_path: Path) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    session_id = uuid4()

    first = _save(repository, index=1, session_id=session_id)
    second = _save(repository, index=2, session_id=session_id)
    third = _save(repository, index=3, session_id=session_id)
    loaded = repository.get(OWNER, first.record_id)

    assert repository.count(OWNER) == 1
    assert first.record_id == second.record_id == third.record_id
    assert loaded.record_id == first.record_id
    assert loaded.session_id == session_id
    assert loaded.turn_count == 3
    assert loaded.user_message == "第 1 个问题"
    assert loaded.latest_user_message == "第 3 个问题"
    assert loaded.answer == "问题判断：第 3 次 DNS 解析异常。"
    assert loaded.created_at == first.created_at
    assert loaded.updated_at >= second.updated_at >= first.updated_at
    assert loaded.metrics.token_usage.prompt_tokens == 36
    assert loaded.metrics.token_usage.completion_tokens == 15
    assert loaded.metrics.token_usage.total_tokens == 51
    assert loaded.metrics.llm_duration_ms == 67.5
    assert loaded.metrics.tool_duration_ms == 12
    assert loaded.metrics.tool_calls == 3
    assert [item.tool_call_id for item in loaded.tool_calls] == [
        "history_dns_1",
        "history_dns_2",
        "history_dns_3",
    ]

    with sqlite3.connect(repository.path) as connection:
        rows = connection.execute(
            "SELECT record_id FROM diagnosis_records "
            "WHERE user_id = ? AND session_id = ?",
            (str(OWNER), str(session_id)),
        ).fetchall()
        indexes = connection.execute(
            "PRAGMA index_list('diagnosis_records')"
        ).fetchall()
    assert rows == [(str(first.record_id),)]
    assert any(
        row[1] == "uq_diagnosis_user_session" and row[2] == 1
        for row in indexes
    )


def test_new_session_creates_a_distinct_history_record(tmp_path: Path) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    session_a = uuid4()
    session_b = uuid4()

    first_a = _save(repository, index=1, session_id=session_a)
    second_a = _save(repository, index=2, session_id=session_a)
    first_b = _save(repository, index=3, session_id=session_b)

    assert repository.count(OWNER) == 2
    assert first_a.record_id == second_a.record_id
    assert first_a.record_id != first_b.record_id
    assert repository.get(OWNER, first_a.record_id).turn_count == 2
    assert repository.get(OWNER, first_b.record_id).turn_count == 1


def _source(name: str) -> KnowledgeSource:
    return KnowledgeSource(
        title=f"Source {name}",
        source=f"https://example.com/{name}",
        source_type="community",
        file=f"{name}.md",
        chunk_id=f"source-{name}-chunk",
        score=0.9,
    )


def test_session_sources_are_merged_and_deduplicated(tmp_path: Path) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    session_id = uuid4()
    first_result = _agent_result(1).model_copy(
        update={"sources": [_source("a")]}
    )
    second_result = _agent_result(2).model_copy(
        update={"sources": [_source("a"), _source("b")]}
    )

    first = repository.upsert_session(
        OWNER,
        "第一次检索",
        present_chat(session_id, first_result),
    )
    repository.upsert_session(
        OWNER,
        "第二次检索",
        present_chat(session_id, second_result),
    )
    loaded = repository.get(OWNER, first.record_id)

    assert [item.chunk_id for item in loaded.sources] == [
        "source-a-chunk",
        "source-b-chunk",
    ]


def test_report_and_meta_turns_preserve_meaningful_diagnosis(tmp_path: Path) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    session_id = uuid4()
    diagnostic = _agent_result(1).model_copy(
        update={
            "turn_intent": TurnIntent.DIAGNOSE,
            "response_mode": ResponseMode.DIAGNOSTIC,
        }
    )
    report = AgentResult(
        answer="现象 / 检测步骤 / 证据 / 排除项 / 初步结论 / 建议",
        status=AgentStatus.COMPLETED,
        tool_rounds=0,
        turn_intent=TurnIntent.REPORT_REQUEST,
        response_mode=ResponseMode.REPORT,
    )
    meta = AgentResult(
        answer="已根据你的反馈修正表述。",
        status=AgentStatus.COMPLETED,
        tool_rounds=0,
        turn_intent=TurnIntent.META_FEEDBACK,
        response_mode=ResponseMode.META,
    )

    first = repository.upsert_session(
        OWNER, "github.com 无法解析", present_chat(session_id, diagnostic)
    )
    repository.upsert_session(
        OWNER, "生成诊断报告", present_chat(session_id, report)
    )
    repository.upsert_session(
        OWNER, "你刚才重复了", present_chat(session_id, meta)
    )
    loaded = repository.get(OWNER, first.record_id)

    assert loaded.turn_count == 3
    assert loaded.diagnosis.primary_issue == "dns_resolution_failure"
    assert loaded.diagnosis.evidence[0].tool == "dns_lookup"
    assert loaded.answer == "已根据你的反馈修正表述。"
    assert loaded.metrics.turn_intent == "meta_feedback"
    assert loaded.metrics.response_mode == "meta"

    assert loaded.conversation_complete is True
    assert len(loaded.conversation_turns) == 3


def test_sqlite_history_enforces_retention_and_cursor_pagination(
    tmp_path: Path,
) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db", max_records=3)
    records = [_save(repository, index=index) for index in range(1, 5)]

    first_page = repository.list(OWNER, limit=2)
    second_page = repository.list(OWNER, limit=2, cursor=first_page.next_cursor)

    assert repository.count(OWNER) == 3
    with pytest.raises(DiagnosisRecordNotFoundError):
        repository.get(OWNER, records[0].record_id)
    assert len(first_page.items) == 2
    assert first_page.next_cursor is not None
    assert len(second_page.items) == 1
    assert second_page.next_cursor is None
    assert {item.record_id for item in first_page.items + second_page.items} == {
        record.record_id for record in records[1:]
    }


def test_sqlite_history_filters_sessions_and_rejects_bad_cursor(tmp_path: Path) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    selected_session = uuid4()
    expected = _save(repository, index=1, session_id=selected_session)
    _save(repository, index=2)

    filtered = repository.list(OWNER, session_id=selected_session)

    assert [item.record_id for item in filtered.items] == [expected.record_id]
    with pytest.raises(DiagnosisCursorError):
        repository.list(OWNER, cursor="not a valid cursor")


def test_history_orders_sessions_by_latest_activity(tmp_path: Path) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    session_a = uuid4()
    session_b = uuid4()
    first_a = _save(repository, index=1, session_id=session_a)
    first_b = _save(repository, index=2, session_id=session_b)

    before_update = repository.list(OWNER)
    updated_a = _save(repository, index=3, session_id=session_a)
    after_update = repository.list(OWNER)

    assert [item.record_id for item in before_update.items] == [
        first_b.record_id,
        first_a.record_id,
    ]
    assert [item.record_id for item in after_update.items] == [
        updated_a.record_id,
        first_b.record_id,
    ]
    assert after_update.items[0].turn_count == 2


def test_sqlite_history_serializes_concurrent_writes(tmp_path: Path) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db", max_records=50)

    with ThreadPoolExecutor(max_workers=8) as executor:
        records = list(
            executor.map(
                lambda index: _save(repository, index=index),
                range(1, 21),
            )
        )

    assert repository.count(OWNER) == 20
    assert len({record.record_id for record in records}) == 20


def test_v2_migration_merges_turn_records_once_without_data_loss(
    tmp_path: Path,
) -> None:
    database = tmp_path / "v2.db"
    user_id = uuid4()
    session_id = uuid4()
    start = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
    source_a = _source("a")
    source_b = _source("b")
    results = [
        _agent_result(1).model_copy(
            update={
                "usage": TokenUsage(
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                ),
                "sources": [source_a],
                "turn_intent": TurnIntent.DIAGNOSE,
                "response_mode": ResponseMode.DIAGNOSTIC,
            }
        ),
        _agent_result(2).model_copy(
            update={
                "usage": TokenUsage(
                    prompt_tokens=200,
                    completion_tokens=75,
                    total_tokens=275,
                ),
                "sources": [source_a, source_b],
                "turn_intent": TurnIntent.DIAGNOSE,
                "response_mode": ResponseMode.DIAGNOSTIC,
            }
        ),
        AgentResult(
            answer="会话诊断报告",
            status=AgentStatus.COMPLETED,
            tool_rounds=0,
            usage=TokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
            turn_intent=TurnIntent.REPORT_REQUEST,
            response_mode=ResponseMode.REPORT,
        ),
        AgentResult(
            answer="最后一轮反馈答复",
            status=AgentStatus.COMPLETED,
            tool_rounds=0,
            usage=TokenUsage(
                prompt_tokens=20,
                completion_tokens=10,
                total_tokens=30,
            ),
            turn_intent=TurnIntent.META_FEEDBACK,
            response_mode=ResponseMode.META,
        ),
    ]
    record_ids = [uuid4() for _ in results]
    records: list[DiagnosisRecordView] = []
    for index, result in enumerate(results):
        response = present_chat(session_id, result)
        timestamp = start + timedelta(minutes=index)
        records.append(
            DiagnosisRecordView(
                schema_version=1,
                record_id=record_ids[index],
                user_id=user_id,
                session_id=session_id,
                created_at=timestamp,
                updated_at=timestamp,
                turn_count=1,
                user_message=f"旧 Turn {index + 1}",
                latest_user_message=f"旧 Turn {index + 1}",
                answer=response.answer,
                diagnosis=response.diagnosis,
                metrics=response.metrics,
                tool_calls=response.tool_calls,
                sources=response.sources,
            )
        )

    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE netpilot_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO netpilot_metadata(key, value) VALUES ('schema_version', '2');
            CREATE TABLE diagnosis_records (
                record_id TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                user_id TEXT,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                user_message TEXT NOT NULL,
                answer_preview TEXT NOT NULL,
                status TEXT NOT NULL,
                primary_issue TEXT NOT NULL,
                confidence TEXT NOT NULL,
                snapshot_json TEXT NOT NULL
            );
            """
        )
        for record in records:
            legacy_snapshot = record.model_dump(
                mode="json",
                exclude={"updated_at", "turn_count", "latest_user_message",
                         "conversation_turns", "conversation_complete"},
            )
            connection.execute(
                """
                INSERT INTO diagnosis_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.record_id),
                    1,
                    str(user_id),
                    str(session_id),
                    record.created_at.isoformat(),
                    record.user_message,
                    record.answer,
                    str(getattr(record.diagnosis.status, "value", record.diagnosis.status)),
                    record.diagnosis.primary_issue,
                    record.diagnosis.confidence,
                    json.dumps(legacy_snapshot, ensure_ascii=False),
                ),
            )

    migrated = SQLiteDiagnosisRepository(database)
    loaded = migrated.get(user_id, record_ids[-1])

    assert migrated.count(user_id) == 1
    assert loaded.record_id == record_ids[-1]
    assert loaded.created_at == start
    assert loaded.updated_at == start + timedelta(minutes=3)
    assert loaded.turn_count == 4
    assert loaded.user_message == "旧 Turn 1"
    assert loaded.latest_user_message == "旧 Turn 4"
    assert loaded.answer == "最后一轮反馈答复"
    assert loaded.metrics.token_usage.prompt_tokens == 330
    assert loaded.metrics.token_usage.completion_tokens == 140
    assert loaded.metrics.token_usage.total_tokens == 470
    assert loaded.metrics.tool_calls == 2
    assert [item.tool_call_id for item in loaded.tool_calls] == [
        "history_dns_1",
        "history_dns_2",
    ]
    assert [item.chunk_id for item in loaded.sources] == [
        "source-a-chunk",
        "source-b-chunk",
    ]
    assert loaded.diagnosis.primary_issue == "dns_resolution_failure"
    assert loaded.metrics.response_mode == "meta"

    assert loaded.conversation_complete is True
    assert len(loaded.conversation_turns) == 4
    assert [turn.assistant_answer for turn in loaded.conversation_turns] == [record.answer for record in records]
    reopened = SQLiteDiagnosisRepository(database)
    repeated = reopened.get(user_id, record_ids[-1])
    assert repeated == loaded
    assert reopened.count(user_id) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value FROM netpilot_metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "3"
        assert connection.execute(
            "SELECT COUNT(*) FROM diagnosis_records "
            "WHERE user_id = ? AND session_id = ?",
            (str(user_id), str(session_id)),
        ).fetchone()[0] == 1


class HistoryAgent:
    def run(self, message: str, *, history=(), task_state=None) -> AgentResult:
        del message, history, task_state
        return _agent_result(7)


def _history_app(database: Path):
    app = create_app(
        Settings(
            _env_file=None,
            tju_api_key="history-test-key",
            tool_mode="mock",
            rag_enabled=False,
            diagnosis_history_enabled=True,
            diagnosis_db_path=database,
            diagnosis_max_records=10,
        )
    )
    app.state.agent = HistoryAgent()
    return app


def test_chat_persists_metrics_and_history_api_survives_restart(tmp_path: Path) -> None:
    database = tmp_path / "netpilot.db"
    first_app = _history_app(database)
    with TestClient(first_app) as client:
        assert client.get("/api/health").json()["history_ready"] is True
        register_test_user(client)
        username = client.get("/api/auth/me").json()["username"]
        session_id = client.post("/api/session").json()["session_id"]
        chat = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "github.com 打不开"},
        )
        listing = client.get("/api/diagnoses?limit=10")

    assert chat.status_code == 200
    body = chat.json()
    assert body["record_id"] is not None
    assert body["metrics"] == {
        "token_usage": {
            "prompt_tokens": 17,
            "completion_tokens": 5,
            "total_tokens": 22,
        },
        "llm_duration_ms": 27.5,
            "tool_duration_ms": 4,
            "tool_calls": 1,
            "turn_intent": None,
            "response_mode": None,
            "fallback_reason": None,
            "rag_calls": 0,
            "knowledge_finalization_attempts": 0,
            "knowledge_finalization_failure_kind": None,
            "history_context_records": 0,
            "network_tool_calls": 1,
        }
    assert listing.json()["items"][0]["record_id"] == body["record_id"]

    second_app = _history_app(database)
    with TestClient(second_app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": username, "password": "test-password-123"},
        )
        assert login.status_code == 200
        detail = client.get(f"/api/diagnoses/{body['record_id']}")

    assert detail.status_code == 200
    assert detail.json()["user_message"] == "github.com 打不开"
    assert detail.json()["metrics"] == body["metrics"]
    assert "history-test-key" not in database.read_bytes().decode(
        "utf-8", errors="ignore"
    )


def test_history_api_handles_disabled_missing_and_invalid_requests(tmp_path: Path) -> None:
    disabled = create_app(
        Settings(
            _env_file=None,
            diagnosis_history_enabled=False,
            rag_enabled=False,
        )
    )
    with TestClient(disabled) as client:
        register_test_user(client)
        unavailable = client.get("/api/diagnoses")

    enabled = _history_app(tmp_path / "history.db")
    with TestClient(enabled) as client:
        register_test_user(client)
        missing = client.get(f"/api/diagnoses/{uuid4()}")
        invalid_cursor = client.get("/api/diagnoses?cursor=invalid")
        invalid_limit = client.get("/api/diagnoses?limit=101")

    assert unavailable.status_code == 503
    assert missing.status_code == 404
    assert invalid_cursor.status_code == 422
    assert invalid_limit.status_code == 422


def test_database_initialization_failure_degrades_application_safely(
    tmp_path: Path,
) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("blocked", encoding="utf-8")
    app = create_app(
        Settings(
            _env_file=None,
            diagnosis_history_enabled=True,
            diagnosis_db_path=blocking_file / "netpilot.db",
            rag_enabled=False,
        )
    )

    with TestClient(app) as client:
        health = client.get("/api/health")
        history = client.get("/api/diagnoses")

    assert health.status_code == 200
    assert health.json()["history_ready"] is False
    assert history.status_code == 503
    assert str(blocking_file) not in history.text


class BrokenRepository:
    def upsert_session(self, *_args: Any, **_kwargs: Any):
        raise DiagnosisStorageError("private database detail")


def test_history_write_failure_does_not_fail_chat(tmp_path: Path) -> None:
    app = _history_app(tmp_path / "history.db")
    app.state.diagnosis_repository = BrokenRepository()
    with TestClient(app) as client:
        register_test_user(client)
        session_id = client.post("/api/session").json()["session_id"]
        response = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "测试历史降级"},
        )

    assert response.status_code == 200
    assert response.json()["record_id"] is None
    assert "private database detail" not in response.text
