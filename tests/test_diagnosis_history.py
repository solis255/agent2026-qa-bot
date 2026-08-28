from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from netpilot.agent import AgentResult, AgentStatus, AgentToolStep
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
from netpilot.tools.schemas import DNSLookupData, ToolResult


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
):
    resolved_session = session_id or uuid4()
    response = present_chat(resolved_session, _agent_result(index))
    return repository.save(f"第 {index} 个问题", response)


def test_sqlite_history_persists_complete_snapshot_across_instances(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history" / "netpilot.db"
    first = SQLiteDiagnosisRepository(database)
    saved = _save(first, index=1)

    reopened = SQLiteDiagnosisRepository(database)
    loaded = reopened.get(saved.record_id)

    assert reopened.count() == 1
    assert loaded == saved
    assert loaded.metrics.token_usage.total_tokens == 16
    assert loaded.metrics.llm_duration_ms == 21.5
    assert loaded.metrics.tool_duration_ms == 4
    assert loaded.metrics.tool_calls == 1
    assert loaded.tool_calls[0].finding_status == "abnormal"


def test_sqlite_history_enforces_retention_and_cursor_pagination(
    tmp_path: Path,
) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db", max_records=3)
    records = [_save(repository, index=index) for index in range(1, 5)]

    first_page = repository.list(limit=2)
    second_page = repository.list(limit=2, cursor=first_page.next_cursor)

    assert repository.count() == 3
    with pytest.raises(DiagnosisRecordNotFoundError):
        repository.get(records[0].record_id)
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

    filtered = repository.list(session_id=selected_session)

    assert [item.record_id for item in filtered.items] == [expected.record_id]
    with pytest.raises(DiagnosisCursorError):
        repository.list(cursor="not a valid cursor")


def test_sqlite_history_serializes_concurrent_writes(tmp_path: Path) -> None:
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db", max_records=50)

    with ThreadPoolExecutor(max_workers=8) as executor:
        records = list(
            executor.map(
                lambda index: _save(repository, index=index),
                range(1, 21),
            )
        )

    assert repository.count() == 20
    assert len({record.record_id for record in records}) == 20


class HistoryAgent:
    def run(self, message: str, *, history=()) -> AgentResult:
        del message, history
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
    }
    assert listing.json()["items"][0]["record_id"] == body["record_id"]

    second_app = _history_app(database)
    with TestClient(second_app) as client:
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
        unavailable = client.get("/api/diagnoses")

    enabled = _history_app(tmp_path / "history.db")
    with TestClient(enabled) as client:
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
    def save(self, *_args: Any, **_kwargs: Any):
        raise DiagnosisStorageError("private database detail")


def test_history_write_failure_does_not_fail_chat(tmp_path: Path) -> None:
    app = _history_app(tmp_path / "history.db")
    app.state.diagnosis_repository = BrokenRepository()
    with TestClient(app) as client:
        session_id = client.post("/api/session").json()["session_id"]
        response = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "测试历史降级"},
        )

    assert response.status_code == 200
    assert response.json()["record_id"] is None
    assert "private database detail" not in response.text
