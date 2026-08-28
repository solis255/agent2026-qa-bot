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

from netpilot.models import (
    ChatResponse,
    DiagnosisHistoryResponse,
    DiagnosisRecordSummaryView,
    DiagnosisRecordView,
)


SCHEMA_VERSION = 1


class DiagnosisStorageError(RuntimeError):
    """Safe base error for unavailable or corrupt diagnosis history."""


class DiagnosisRecordNotFoundError(DiagnosisStorageError):
    """Raised when a diagnosis record does not exist."""


class DiagnosisCursorError(DiagnosisStorageError):
    """Raised when a list cursor is malformed."""


class DiagnosisRepository(Protocol):
    """Persistence boundary used by the API and replaceable in tests."""

    def save(self, user_message: str, response: ChatResponse) -> DiagnosisRecordView: ...

    def get(self, record_id: UUID) -> DiagnosisRecordView: ...

    def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        session_id: UUID | None = None,
    ) -> DiagnosisHistoryResponse: ...


class SQLiteDiagnosisRepository:
    """Persist bounded immutable snapshots using Python's bundled SQLite."""

    def __init__(self, path: Path, *, max_records: int = 1000) -> None:
        if max_records < 1:
            raise ValueError("max_records must be at least 1")
        self.path = Path(path)
        self.max_records = max_records
        self._lock = RLock()
        self._initialize()

    def save(self, user_message: str, response: ChatResponse) -> DiagnosisRecordView:
        record_id = uuid4()
        created_at = datetime.now(timezone.utc)
        record = DiagnosisRecordView(
            record_id=record_id,
            session_id=response.session_id,
            created_at=created_at,
            user_message=user_message,
            answer=response.answer,
            diagnosis=response.diagnosis,
            metrics=response.metrics,
            tool_calls=response.tool_calls,
            sources=response.sources,
        )
        preview = _preview(response.answer)
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO diagnosis_records (
                        record_id, schema_version, session_id, created_at,
                        user_message, answer_preview, status, primary_issue,
                        confidence, snapshot_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(record_id),
                        SCHEMA_VERSION,
                        str(response.session_id),
                        created_at.isoformat(),
                        user_message,
                        preview,
                        str(
                            getattr(
                                response.diagnosis.status,
                                "value",
                                response.diagnosis.status,
                            )
                        ),
                        response.diagnosis.primary_issue,
                        response.diagnosis.confidence,
                        record.model_dump_json(),
                    ),
                )
                connection.execute(
                    """
                    DELETE FROM diagnosis_records
                    WHERE record_id IN (
                        SELECT record_id FROM diagnosis_records
                        ORDER BY created_at DESC, record_id DESC
                        LIMIT -1 OFFSET ?
                    )
                    """,
                    (self.max_records,),
                )
        except sqlite3.Error as exc:
            raise DiagnosisStorageError("诊断历史写入失败") from exc
        return record

    def get(self, record_id: UUID) -> DiagnosisRecordView:
        try:
            with self._lock, self._connection() as connection:
                row = connection.execute(
                    "SELECT snapshot_json FROM diagnosis_records WHERE record_id = ?",
                    (str(record_id),),
                ).fetchone()
        except sqlite3.Error as exc:
            raise DiagnosisStorageError("诊断历史读取失败") from exc
        if row is None:
            raise DiagnosisRecordNotFoundError(str(record_id))
        try:
            return DiagnosisRecordView.model_validate_json(row["snapshot_json"])
        except ValidationError as exc:
            raise DiagnosisStorageError("诊断历史数据损坏") from exc

    def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        session_id: UUID | None = None,
    ) -> DiagnosisHistoryResponse:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        cursor_value = _decode_cursor(cursor) if cursor else None
        clauses: list[str] = []
        parameters: list[object] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            parameters.append(str(session_id))
        if cursor_value is not None:
            created_at, record_id = cursor_value
            clauses.append("(created_at < ? OR (created_at = ? AND record_id < ?))")
            parameters.extend([created_at, created_at, record_id])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit + 1)
        try:
            with self._lock, self._connection() as connection:
                rows = connection.execute(
                    f"""
                    SELECT record_id, session_id, created_at, user_message,
                           answer_preview, status, primary_issue, confidence,
                           snapshot_json
                    FROM diagnosis_records
                    {where}
                    ORDER BY created_at DESC, record_id DESC
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
                snapshot = DiagnosisRecordView.model_validate_json(row["snapshot_json"])
                items.append(
                    DiagnosisRecordSummaryView(
                        record_id=UUID(row["record_id"]),
                        session_id=UUID(row["session_id"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                        user_message=row["user_message"],
                        answer_preview=row["answer_preview"],
                        status=row["status"],
                        primary_issue=row["primary_issue"],
                        confidence=row["confidence"],
                        metrics=snapshot.metrics,
                    )
                )
        except (ValidationError, ValueError) as exc:
            raise DiagnosisStorageError("诊断历史数据损坏") from exc

        next_cursor = None
        if has_more and visible_rows:
            last = visible_rows[-1]
            next_cursor = _encode_cursor(last["created_at"], last["record_id"])
        return DiagnosisHistoryResponse(items=items, next_cursor=next_cursor)

    def count(self) -> int:
        try:
            with self._lock, self._connection() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM diagnosis_records"
                ).fetchone()
        except sqlite3.Error as exc:
            raise DiagnosisStorageError("诊断历史读取失败") from exc
        return int(row["count"])

    def _initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self._connection() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS netpilot_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS diagnosis_records (
                        record_id TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL,
                        session_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        user_message TEXT NOT NULL,
                        answer_preview TEXT NOT NULL,
                        status TEXT NOT NULL,
                        primary_issue TEXT NOT NULL,
                        confidence TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_diagnosis_records_created
                    ON diagnosis_records(created_at DESC, record_id DESC)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_diagnosis_records_session
                    ON diagnosis_records(session_id, created_at DESC)
                    """
                )
                row = connection.execute(
                    "SELECT value FROM netpilot_metadata WHERE key = 'schema_version'"
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO netpilot_metadata(key, value) VALUES (?, ?)",
                        ("schema_version", str(SCHEMA_VERSION)),
                    )
                elif int(row["value"]) != SCHEMA_VERSION:
                    raise DiagnosisStorageError("不支持的诊断历史数据库版本")
        except (OSError, sqlite3.Error, ValueError) as exc:
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


def _preview(value: str, limit: int = 240) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[:limit]}…"


def _encode_cursor(created_at: str, record_id: str) -> str:
    payload = json.dumps([created_at, record_id], separators=(",", ":")).encode()
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
        created_at = datetime.fromisoformat(value[0]).isoformat()
        record_id = str(UUID(value[1]))
    except (
        binascii.Error,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise DiagnosisCursorError("历史记录游标不合法") from exc
    return created_at, record_id
