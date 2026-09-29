"""SQLite user and server-side auth-session repositories."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from netpilot.auth.models import UserRecord


class AuthStorageError(RuntimeError):
    """Safe error for unavailable authentication storage."""


class UsernameExistsError(AuthStorageError):
    """The canonical username already exists."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _SQLiteRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = RLock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AuthStorageError("认证数据库不可用。") from exc

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            return connection
        except sqlite3.Error as exc:
            raise AuthStorageError("认证数据库不可用。") from exc

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _user_from_row(row: sqlite3.Row | None) -> UserRecord | None:
    if row is None:
        return None
    try:
        return UserRecord(
            id=UUID(row["id"]),
            username=row["username"],
            password_hash=row["password_hash"],
            nickname=row["nickname"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_login_at=(
                datetime.fromisoformat(row["last_login_at"])
                if row["last_login_at"] else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthStorageError("用户数据已损坏。") from exc


class UserRepository(_SQLiteRepository):
    """Keep Argon2id hashes and public account metadata in SQLite."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._initialize()

    def _initialize(self) -> None:
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        nickname TEXT,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_login_at TEXT
                    )
                    """
                )
                columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(users)")
                }
                required = {
                    "id", "username", "password_hash", "nickname", "is_active",
                    "created_at", "updated_at", "last_login_at",
                }
                if not required <= columns:
                    raise AuthStorageError("用户表结构不兼容。")
        except sqlite3.Error as exc:
            raise AuthStorageError("用户表初始化失败。") from exc

    def create(self, username: str, password_hash: str, nickname: str | None) -> UserRecord:
        user_id = uuid4()
        now = _now().isoformat()
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO users (id, username, password_hash, nickname,
                                       is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (str(user_id), username, password_hash, nickname, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise UsernameExistsError("用户名已存在。") from exc
        except sqlite3.Error as exc:
            raise AuthStorageError("用户注册失败。") from exc
        record = self.get_by_id(user_id)
        if record is None:
            raise AuthStorageError("用户记录不存在。")
        return record

    def get_by_username(self, username: str) -> UserRecord | None:
        return self._get("username", username)

    def get_by_id(self, user_id: UUID) -> UserRecord | None:
        return self._get("id", str(user_id))

    def _get(self, column: str, value: str) -> UserRecord | None:
        # column is selected only by the two internal callers above.
        try:
            with self._lock, self._connection() as connection:
                row = connection.execute(
                    f"SELECT * FROM users WHERE {column} = ?", (value,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise AuthStorageError("用户读取失败。") from exc
        return _user_from_row(row)

    def record_login(self, user_id: UUID) -> UserRecord:
        now = _now().isoformat()
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, str(user_id)),
                )
        except sqlite3.Error as exc:
            raise AuthStorageError("登录状态更新失败。") from exc
        record = self.get_by_id(user_id)
        if record is None:
            raise AuthStorageError("用户记录不存在。")
        return record

    def change_password(self, user_id: UUID, password_hash: str) -> None:
        try:
            with self._lock, self._connection() as connection:
                result = connection.execute(
                    "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                    (password_hash, _now().isoformat(), str(user_id)),
                )
                if result.rowcount != 1:
                    raise AuthStorageError("用户记录不存在。")
        except sqlite3.Error as exc:
            raise AuthStorageError("密码修改失败。") from exc


class AuthSessionRepository(_SQLiteRepository):
    """Store hashed opaque tokens, expiry and revocation state."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self._initialize()

    def _initialize(self) -> None:
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auth_sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        token_hash TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        last_seen_at TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(id)
                    )
                    """
                )
                columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(auth_sessions)")
                }
                required = {
                    "id", "user_id", "token_hash", "created_at",
                    "expires_at", "last_seen_at",
                }
                if not required <= columns:
                    raise AuthStorageError("认证会话表结构不兼容。")
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user "
                    "ON auth_sessions(user_id, created_at DESC)"
                )
        except sqlite3.Error as exc:
            raise AuthStorageError("认证会话表初始化失败。") from exc

    def create(
        self,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        *,
        max_active: int,
    ) -> None:
        now = _now().isoformat()
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    "DELETE FROM auth_sessions WHERE user_id = ? AND expires_at <= ?",
                    (str(user_id), now),
                )
                connection.execute(
                    """
                    INSERT INTO auth_sessions
                        (id, user_id, token_hash, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(uuid4()), str(user_id), token_hash, now, expires_at.isoformat()),
                )
                connection.execute(
                    """
                    DELETE FROM auth_sessions WHERE id IN (
                        SELECT id FROM auth_sessions WHERE user_id = ?
                        ORDER BY created_at DESC, rowid DESC LIMIT -1 OFFSET ?
                    )
                    """,
                    (str(user_id), max_active),
                )
        except sqlite3.Error as exc:
            raise AuthStorageError("认证会话创建失败。") from exc

    def user_id_for_token(self, token_hash: str) -> UUID | None:
        try:
            with self._lock, self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT s.user_id FROM auth_sessions AS s
                    JOIN users AS u ON u.id = s.user_id
                    WHERE s.token_hash = ? AND s.expires_at > ? AND u.is_active = 1
                    """,
                    (token_hash, _now().isoformat()),
                ).fetchone()
        except sqlite3.Error as exc:
            raise AuthStorageError("认证会话读取失败。") from exc
        if row is None:
            return None
        try:
            return UUID(row["user_id"])
        except ValueError as exc:
            raise AuthStorageError("认证会话数据已损坏。") from exc

    def revoke(self, token_hash: str) -> None:
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    "DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,)
                )
        except sqlite3.Error as exc:
            raise AuthStorageError("认证会话撤销失败。") from exc

    def revoke_all(self, user_id: UUID) -> None:
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    "DELETE FROM auth_sessions WHERE user_id = ?", (str(user_id),)
                )
        except sqlite3.Error as exc:
            raise AuthStorageError("认证会话撤销失败。") from exc
