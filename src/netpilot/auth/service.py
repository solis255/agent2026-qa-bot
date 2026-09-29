"""Auth operations shared by the API and future resource-ownership layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from netpilot.auth.models import UserRecord
from netpilot.auth.password import hash_password, verify_password
from netpilot.auth.repository import AuthSessionRepository, UserRepository
from netpilot.auth.sessions import create_session_token, hash_session_token


class InvalidCredentialsError(RuntimeError):
    """Do not reveal whether an account exists or which credential failed."""


class AuthService:
    def __init__(self, database: Path, *, session_hours: int, max_sessions: int) -> None:
        self.users = UserRepository(database)
        self.sessions = AuthSessionRepository(database)
        self.session_hours = session_hours
        self.max_sessions = max_sessions

    def register(
        self, username: str, password: str, nickname: str | None
    ) -> tuple[UserRecord, str]:
        user = self.users.create(username, hash_password(password), nickname)
        token = self._issue(user.id)
        return self.users.record_login(user.id), token

    def login(self, username: str, password: str) -> tuple[UserRecord, str]:
        if len(username) > 32 or len(password) > 128:
            raise InvalidCredentialsError("用户名或密码错误。")
        user = self.users.get_by_username(username)
        if not verify_password(user.password_hash if user else None, password):
            raise InvalidCredentialsError("用户名或密码错误。")
        if user is None or not user.is_active:
            raise InvalidCredentialsError("用户名或密码错误。")
        token = self._issue(user.id)
        return self.users.record_login(user.id), token

    def current_user(self, token: str | None) -> UserRecord | None:
        if not token or len(token) > 256:
            return None
        user_id = self.sessions.user_id_for_token(hash_session_token(token))
        return self.users.get_by_id(user_id) if user_id is not None else None

    def logout(self, token: str | None) -> None:
        if token and len(token) <= 256:
            self.sessions.revoke(hash_session_token(token))

    def change_password(
        self, user: UserRecord, old_password: str, new_password: str
    ) -> str:
        # Re-read the current hash so another password change invalidates stale forms.
        latest = self.users.get_by_id(user.id)
        if latest is None or not latest.is_active or not verify_password(
            latest.password_hash, old_password
        ):
            raise InvalidCredentialsError("原密码错误。")
        self.users.change_password(user.id, hash_password(new_password))
        self.sessions.revoke_all(user.id)
        return self._issue(user.id)

    def _issue(self, user_id: UUID) -> str:
        token, token_hash = create_session_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.session_hours)
        self.sessions.create(
            user_id, token_hash, expires_at, max_active=self.max_sessions
        )
        return token
