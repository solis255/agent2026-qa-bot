"""Versioned SQLite persistence for structured diagnosis snapshots."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError
from netpilot.agent.reasoning_trace import merge_reasoning_trace, trim_reasoning_trace

from netpilot.models import (
    ChatResponse,
    DiagnosisHistoryResponse,
    DiagnosisRecordSummaryView,
    DiagnosisRecordView,
    ExecutionMetricsView,
    TokenUsageView,
    PersistedConversationTurn,
)


SCHEMA_VERSION = 3
SNAPSHOT_SCHEMA_VERSION = 4


class DiagnosisStorageError(RuntimeError):
    """Safe base error for unavailable or corrupt diagnosis history."""


class DiagnosisRecordNotFoundError(DiagnosisStorageError):
    """Raised when a diagnosis record does not exist."""


class DiagnosisCursorError(DiagnosisStorageError):
    """Raised when a list cursor is malformed."""


class DiagnosisRepository(Protocol):
    """Persistence boundary used by the API and replaceable in tests."""

    def upsert_session(
        self, user_id: UUID, user_message: str, response: ChatResponse
    ) -> DiagnosisRecordView: ...

    def save(
        self, user_id: UUID, user_message: str, response: ChatResponse
    ) -> DiagnosisRecordView: ...

    def get(self, user_id: UUID, record_id: UUID) -> DiagnosisRecordView: ...

    def query_context_records(
        self, user_id: UUID, *, start_at: datetime | None = None,
        end_at: datetime | None = None, limit: int = 5,
    ) -> list[DiagnosisRecordView]: ...

    def list(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        session_id: UUID | None = None,
    ) -> DiagnosisHistoryResponse: ...


class SQLiteDiagnosisRepository:
    """Persist one bounded cumulative diagnosis snapshot per user Session."""

    def __init__(self, path: Path, *, max_records: int = 1000, reasoning_trace_max_steps: int = 50) -> None:
        if max_records < 1:
            raise ValueError("max_records must be at least 1")
        self.path = Path(path)
        self.max_records = max_records
        if not 1 <= reasoning_trace_max_steps <= 200:
            raise ValueError("reasoning_trace_max_steps must be between 1 and 200")
        self.reasoning_trace_max_steps = reasoning_trace_max_steps
        self._lock = RLock()
        self._initialize()

    def upsert_session(
        self, user_id: UUID, user_message: str, response: ChatResponse
    ) -> DiagnosisRecordView:
        """Insert the first Turn, then update the stable user/session record."""

        now = datetime.now(timezone.utc)
        current = DiagnosisRecordView(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            record_id=uuid4(),
            user_id=user_id,
            session_id=response.session_id,
            created_at=now,
            updated_at=now,
            turn_count=1,
            user_message=user_message,
            latest_user_message=user_message,
            answer=response.answer,
            diagnosis=response.diagnosis,
            metrics=response.metrics.model_copy(update={
                "reasoning_trace_steps": min(len(response.reasoning_trace), self.reasoning_trace_max_steps),
            }),
            tool_calls=response.tool_calls,
            sources=response.sources,
            conversation_turns=[PersistedConversationTurn(
                turn_index=1, user_message=user_message,
                assistant_answer=response.answer, created_at=now,
                turn_intent=response.metrics.turn_intent,
                response_mode=response.metrics.response_mode,
                fallback_reason=response.metrics.fallback_reason,
                knowledge_finalization_failure_kind=response.metrics.knowledge_finalization_failure_kind,
            )],
            conversation_complete=True,
            reasoning_trace=trim_reasoning_trace(response.reasoning_trace, self.reasoning_trace_max_steps),
        )
        try:
            with self._lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM diagnosis_records "
                    "WHERE user_id = ? AND session_id = ?",
                    (str(user_id), str(response.session_id)),
                ).fetchone()
                if row is None:
                    record = current
                    _insert_record(connection, record)
                else:
                    existing = _record_from_row(row)
                    record = _merge_session_records(existing, current, reasoning_trace_max_steps=self.reasoning_trace_max_steps)
                    _update_record(connection, record)
                connection.execute(
                    """
                    DELETE FROM diagnosis_records
                    WHERE record_id IN (
                        SELECT record_id FROM diagnosis_records
                        WHERE user_id IS NOT NULL
                        ORDER BY updated_at DESC, record_id DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (self.max_records,),
                )
        except (
            sqlite3.Error,
            ValidationError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise DiagnosisStorageError("诊断历史写入失败") from exc
        return record

    def save(
        self, user_id: UUID, user_message: str, response: ChatResponse
    ) -> DiagnosisRecordView:
        """Backward-compatible wrapper for callers outside the API path."""

        return self.upsert_session(user_id, user_message, response)

    def get(self, user_id: UUID, record_id: UUID) -> DiagnosisRecordView:
        try:
            with self._lock, self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM diagnosis_records "
                    "WHERE record_id = ? AND user_id = ?",
                    (str(record_id), str(user_id)),
                ).fetchone()
        except sqlite3.Error as exc:
            raise DiagnosisStorageError("诊断历史读取失败") from exc
        if row is None:
            raise DiagnosisRecordNotFoundError(str(record_id))
        try:
            record = _record_from_row(row)
            if record.user_id != user_id:
                raise DiagnosisStorageError("诊断历史数据损坏")
            return record
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise DiagnosisStorageError("诊断历史数据损坏") from exc

    def list(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        session_id: UUID | None = None,
    ) -> DiagnosisHistoryResponse:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        cursor_value = _decode_cursor(cursor) if cursor else None
        clauses: list[str] = ["user_id = ?"]
        parameters: list[object] = [str(user_id)]
        if session_id is not None:
            clauses.append("session_id = ?")
            parameters.append(str(session_id))
        if cursor_value is not None:
            updated_at, record_id = cursor_value
            clauses.append("(updated_at < ? OR (updated_at = ? AND record_id < ?))")
            parameters.extend([updated_at, updated_at, record_id])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit + 1)
        try:
            with self._lock, self._connection() as connection:
                rows = connection.execute(
                    f"""
                    SELECT *
                    FROM diagnosis_records
                    {where}
                    ORDER BY updated_at DESC, record_id DESC
                    LIMIT ?
                    """,  # noqa: S608 - only fixed clauses are interpolated
                    parameters,
                ).fetchall()
        except sqlite3.Error as exc:
            raise DiagnosisStorageError("诊断历史读取失败") from exc

        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        items: list[DiagnosisRecordSummaryView] = []
        try:
            for row in visible_rows:
                snapshot = _record_from_row(row)
                if snapshot.user_id != user_id:
                    raise DiagnosisStorageError("诊断历史数据损坏")
                items.append(
                    DiagnosisRecordSummaryView(
                        record_id=UUID(row["record_id"]),
                        session_id=UUID(row["session_id"]),
                        created_at=snapshot.created_at,
                        updated_at=snapshot.updated_at,
                        turn_count=snapshot.turn_count,
                        user_message=snapshot.user_message,
                        latest_user_message=snapshot.latest_user_message,
                        answer_preview=row["answer_preview"],
                        status=row["status"],
                        primary_issue=row["primary_issue"],
                        confidence=row["confidence"],
                        metrics=snapshot.metrics,
                    )
                )
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise DiagnosisStorageError("诊断历史数据损坏") from exc

        next_cursor = None
        if has_more and visible_rows:
            last = visible_rows[-1]
            next_cursor = _encode_cursor(last["updated_at"], last["record_id"])
        return DiagnosisHistoryResponse(items=items, next_cursor=next_cursor)

    def query_context_records(
        self, user_id: UUID, *, start_at: datetime | None = None,
        end_at: datetime | None = None, limit: int = 5,
    ) -> list[DiagnosisRecordView]:
        """Fetch only this owner's meaningful Session diagnoses, bounded in SQL."""

        if not 1 <= limit <= 10:
            raise ValueError("context limit must be between 1 and 10")
        clauses = ["user_id = ?", "primary_issue != 'undetermined'"]
        parameters: list[object] = [str(user_id)]
        if start_at is not None:
            clauses.append("updated_at >= ?")
            parameters.append(start_at.isoformat())
        if end_at is not None:
            clauses.append("updated_at < ?")
            parameters.append(end_at.isoformat())
        parameters.append(limit)
        try:
            with self._lock, self._connection() as connection:
                rows = connection.execute(
                    "SELECT * FROM diagnosis_records WHERE " + " AND ".join(clauses)
                    + " ORDER BY updated_at DESC, record_id DESC LIMIT ?",
                    parameters,
                ).fetchall()
            return [_record_from_row(row) for row in rows]
        except (sqlite3.Error, ValueError, ValidationError) as exc:
            raise DiagnosisStorageError("诊断历史上下文读取失败") from exc

    def count(self, user_id: UUID) -> int:
        try:
            with self._lock, self._connection() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM diagnosis_records WHERE user_id = ?",
                    (str(user_id),),
                ).fetchone()
        except sqlite3.Error as exc:
            raise DiagnosisStorageError("诊断历史读取失败") from exc
        return int(row["count"])

    def _initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self._connection() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS netpilot_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                version_row = connection.execute(
                    "SELECT value FROM netpilot_metadata WHERE key = 'schema_version'"
                ).fetchone()
                if version_row is not None:
                    version = int(version_row["value"])
                    if version not in {1, 2, SCHEMA_VERSION}:
                        raise DiagnosisStorageError("不支持的诊断历史数据库版本")
                else:
                    version = SCHEMA_VERSION
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS diagnosis_records (
                        record_id TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL,
                        user_id TEXT,
                        session_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        turn_count INTEGER NOT NULL,
                        user_message TEXT NOT NULL,
                        latest_user_message TEXT NOT NULL,
                        answer_preview TEXT NOT NULL,
                        status TEXT NOT NULL,
                        primary_issue TEXT NOT NULL,
                        confidence TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL
                    )
                    """
                )
                columns = {
                    item["name"]
                    for item in connection.execute("PRAGMA table_info(diagnosis_records)")
                }
                required_columns = {
                    "record_id", "schema_version", "session_id", "created_at",
                    "user_message", "answer_preview", "status", "primary_issue",
                    "confidence", "snapshot_json",
                }
                if not required_columns <= columns:
                    raise DiagnosisStorageError("诊断历史数据库表结构不兼容")
                if "user_id" not in columns:
                    connection.execute(
                        "ALTER TABLE diagnosis_records ADD COLUMN user_id TEXT"
                    )
                if "updated_at" not in columns:
                    connection.execute(
                        "ALTER TABLE diagnosis_records ADD COLUMN updated_at TEXT"
                    )
                if "turn_count" not in columns:
                    connection.execute(
                        "ALTER TABLE diagnosis_records "
                        "ADD COLUMN turn_count INTEGER NOT NULL DEFAULT 1"
                    )
                if "latest_user_message" not in columns:
                    connection.execute(
                        "ALTER TABLE diagnosis_records "
                        "ADD COLUMN latest_user_message TEXT"
                    )
                connection.execute(
                    """
                    UPDATE diagnosis_records
                    SET updated_at = COALESCE(updated_at, created_at),
                        latest_user_message = COALESCE(latest_user_message, user_message),
                        turn_count = CASE WHEN turn_count < 1 THEN 1 ELSE turn_count END
                    """
                )
                if version < SCHEMA_VERSION:
                    _migrate_authenticated_records_to_v3(connection)
                connection.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_diagnosis_user_session
                    ON diagnosis_records(user_id, session_id)
                    WHERE user_id IS NOT NULL
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_diagnosis_records_updated
                    ON diagnosis_records(updated_at DESC, record_id DESC)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_diagnosis_records_session
                    ON diagnosis_records(session_id, updated_at DESC)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_diagnosis_records_user_updated
                    ON diagnosis_records(user_id, updated_at DESC, record_id DESC)
                    """
                )
                if version_row is None:
                    connection.execute(
                        "INSERT INTO netpilot_metadata(key, value) VALUES (?, ?)",
                        ("schema_version", str(SCHEMA_VERSION)),
                    )
                elif version < SCHEMA_VERSION:
                    connection.execute(
                        "UPDATE netpilot_metadata SET value = ? WHERE key = 'schema_version'",
                        (str(SCHEMA_VERSION),),
                    )
        except DiagnosisStorageError:
            raise
        except (
            OSError,
            sqlite3.Error,
            ValueError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            raise DiagnosisStorageError("诊断历史数据库初始化失败") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _merge_session_records(
    existing: DiagnosisRecordView,
    current: DiagnosisRecordView,
    *,
    keep_latest_record_id: bool = False,
    reasoning_trace_max_steps: int = 50,
) -> DiagnosisRecordView:
    traced_ids = {identifier for step in [*existing.reasoning_trace, *current.reasoning_trace] for identifier in step.evidence_ids}
    tool_calls = _merge_tool_calls(existing.tool_calls, current.tool_calls, traced_ids=traced_ids)
    sources = _merge_sources(existing.sources, current.sources)
    trace = merge_reasoning_trace(existing.reasoning_trace, [
        step.model_copy(update={"turn_index": existing.turn_count + step.turn_index})
        if step.turn_index <= current.turn_count else step
        for step in current.reasoning_trace
    ], reasoning_trace_max_steps)
    return DiagnosisRecordView(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        record_id=(current.record_id if keep_latest_record_id else existing.record_id),
        user_id=existing.user_id,
        session_id=existing.session_id,
        created_at=min(existing.created_at, current.created_at),
        updated_at=max(existing.updated_at, current.updated_at),
        turn_count=existing.turn_count + current.turn_count,
        user_message=existing.user_message,
        latest_user_message=current.latest_user_message,
        answer=current.answer,
        diagnosis=_merge_session_diagnosis(existing, current),
        metrics=_merge_metrics(existing.metrics, current.metrics, tool_calls).model_copy(update={"reasoning_trace_steps": len(trace)}),
        tool_calls=tool_calls,
        sources=sources,
        conversation_turns=[
            *existing.conversation_turns,
            *(turn.model_copy(update={
                "turn_index": existing.turn_count + turn.turn_index,
            }) for turn in current.conversation_turns),
        ],
        conversation_complete=existing.conversation_complete and current.conversation_complete,
        reasoning_trace=trace,
    )


def _merge_session_diagnosis(
    existing: DiagnosisRecordView,
    current: DiagnosisRecordView,
):
    """Keep the latest meaningful diagnostic/analysis conclusion."""

    mode = current.metrics.response_mode
    meaningful = (
        current.diagnosis.primary_issue != "undetermined"
        or bool(current.diagnosis.evidence)
    )
    if mode in {"diagnostic", "analysis"} and meaningful:
        return current.diagnosis
    if mode is None and meaningful:
        return current.diagnosis
    return existing.diagnosis


def _merge_metrics(
    existing: ExecutionMetricsView,
    current: ExecutionMetricsView,
    tool_calls: list,
) -> ExecutionMetricsView:
    return ExecutionMetricsView(
        token_usage=TokenUsageView(
            prompt_tokens=(
                existing.token_usage.prompt_tokens
                + current.token_usage.prompt_tokens
            ),
            completion_tokens=(
                existing.token_usage.completion_tokens
                + current.token_usage.completion_tokens
            ),
            total_tokens=(
                existing.token_usage.total_tokens
                + current.token_usage.total_tokens
            ),
        ),
        llm_duration_ms=existing.llm_duration_ms + current.llm_duration_ms,
        tool_duration_ms=(
            existing.tool_duration_ms + current.tool_duration_ms
        ),
        tool_calls=len(tool_calls),
        network_tool_calls=sum(call.tool_name != "knowledge_search" for call in tool_calls),
        turn_intent=current.turn_intent,
        response_mode=current.response_mode,
        fallback_reason=current.fallback_reason,
        rag_calls=existing.rag_calls + current.rag_calls,
        knowledge_finalization_attempts=(
            existing.knowledge_finalization_attempts + current.knowledge_finalization_attempts
        ),
        history_context_records=current.history_context_records,
        knowledge_finalization_failure_kind=current.knowledge_finalization_failure_kind,
        reasoning_summary_llm_used=existing.reasoning_summary_llm_used or current.reasoning_summary_llm_used,
        reasoning_summary_prompt_tokens=existing.reasoning_summary_prompt_tokens + current.reasoning_summary_prompt_tokens,
        reasoning_summary_completion_tokens=existing.reasoning_summary_completion_tokens + current.reasoning_summary_completion_tokens,
    )


def _merge_tool_calls(existing, current, *, traced_ids=frozenset()):
    merged = []
    seen: set[str] = set()
    for tool_call in [*existing, *current]:
        # Keep legacy/untraced dedup semantics. Traced observations need durable
        # identities even if a model reuses its transport call ID in a later Turn.
        identity = tool_call.evidence_id if tool_call.evidence_id in traced_ids else tool_call.tool_call_id
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(tool_call)
    return merged


def _merge_sources(existing, current):
    merged = []
    seen: set[str] = set()
    for source in [*existing, *current]:
        key = source.source_ref
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return merged


def _migrate_authenticated_records_to_v3(
    connection: sqlite3.Connection,
) -> None:
    rows = connection.execute(
        "SELECT * FROM diagnosis_records WHERE user_id IS NOT NULL "
        "ORDER BY user_id, session_id, created_at, record_id"
    ).fetchall()
    groups: dict[tuple[str, str], list[DiagnosisRecordView]] = {}
    for row in rows:
        record = _record_from_row(row)
        if record.user_id is None:
            raise ValueError("authenticated history row has no user_id")
        groups.setdefault(
            (str(record.user_id), str(record.session_id)),
            [],
        ).append(record)

    for records in groups.values():
        merged = records[0].model_copy(
            update={"schema_version": SNAPSHOT_SCHEMA_VERSION}
        )
        for current in records[1:]:
            merged = _merge_session_records(
                merged,
                current,
                keep_latest_record_id=True,
            )
        record_ids = [str(record.record_id) for record in records]
        placeholders = ",".join("?" for _ in record_ids)
        connection.execute(
            f"DELETE FROM diagnosis_records WHERE record_id IN ({placeholders})",  # noqa: S608
            record_ids,
        )
        _insert_record(connection, merged)


def _record_from_row(row: sqlite3.Row) -> DiagnosisRecordView:
    payload = json.loads(row["snapshot_json"])
    if not isinstance(payload, dict):
        raise ValueError("snapshot must be a JSON object")
    payload.update(
        {
            "record_id": row["record_id"],
            "user_id": row["user_id"],
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] or row["created_at"],
            "turn_count": row["turn_count"],
            "user_message": row["user_message"],
            "latest_user_message": (
                row["latest_user_message"] or row["user_message"]
            ),
        }
    )
    return DiagnosisRecordView.model_validate(payload)


def _insert_record(
    connection: sqlite3.Connection,
    record: DiagnosisRecordView,
) -> None:
    connection.execute(
        """
        INSERT INTO diagnosis_records (
            record_id, schema_version, user_id, session_id,
            created_at, updated_at, turn_count, user_message,
            latest_user_message, answer_preview, status,
            primary_issue, confidence, snapshot_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _record_values(record),
    )


def _update_record(
    connection: sqlite3.Connection,
    record: DiagnosisRecordView,
) -> None:
    values = _record_values(record)
    connection.execute(
        """
        UPDATE diagnosis_records SET
            schema_version = ?, user_id = ?, session_id = ?,
            created_at = ?, updated_at = ?, turn_count = ?,
            user_message = ?, latest_user_message = ?, answer_preview = ?,
            status = ?, primary_issue = ?, confidence = ?, snapshot_json = ?
        WHERE record_id = ?
        """,
        (*values[1:], values[0]),
    )


def _record_values(record: DiagnosisRecordView) -> tuple[object, ...]:
    return (
        str(record.record_id),
        SNAPSHOT_SCHEMA_VERSION,
        str(record.user_id) if record.user_id is not None else None,
        str(record.session_id),
        record.created_at.isoformat(),
        record.updated_at.isoformat(),
        record.turn_count,
        record.user_message,
        record.latest_user_message,
        _preview(record.answer),
        str(getattr(record.diagnosis.status, "value", record.diagnosis.status)),
        record.diagnosis.primary_issue,
        record.diagnosis.confidence,
        record.model_copy(
            update={"schema_version": SNAPSHOT_SCHEMA_VERSION}
        ).model_dump_json(),
    )


def _preview(value: str, limit: int = 240) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[:limit]}…"


def _encode_cursor(updated_at: str, record_id: str) -> str:
    payload = json.dumps([updated_at, record_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    if not cursor or len(cursor) > 512:
        raise DiagnosisCursorError("历史记录游标不合法")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        value = json.loads(payload)
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError
        updated_at = datetime.fromisoformat(value[0]).isoformat()
        record_id = str(UUID(value[1]))
    except (
        binascii.Error,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise DiagnosisCursorError("历史记录游标不合法") from exc
    return updated_at, record_id
