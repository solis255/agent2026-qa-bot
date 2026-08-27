"""Thread-safe in-memory conversation sessions for the Web demo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4

from netpilot.llm import ChatMessage, ChatRole


class SessionNotFoundError(KeyError):
    """Raised when a client references an unknown or cleared session."""


class SessionBusyError(RuntimeError):
    """Raised when a second request targets an active session."""


@dataclass
class SessionState:
    session_id: UUID
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessage] = field(default_factory=list)
    busy: bool = False


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: UUID
    created_at: datetime
    updated_at: datetime
    message_count: int
    busy: bool


class SessionStore:
    """Keep bounded user/assistant history without persisting credentials."""

    def __init__(self, *, max_history_messages: int = 20) -> None:
        if max_history_messages < 1:
            raise ValueError("max_history_messages must be at least 1")
        self.max_history_messages = max_history_messages
        self._sessions: dict[UUID, SessionState] = {}
        self._lock = RLock()

    def create(self) -> SessionSnapshot:
        now = datetime.now(timezone.utc)
        state = SessionState(session_id=uuid4(), created_at=now, updated_at=now)
        with self._lock:
            self._sessions[state.session_id] = state
        return _snapshot(state)

    def get(self, session_id: UUID) -> SessionSnapshot:
        with self._lock:
            return _snapshot(self._require(session_id))

    def begin_turn(self, session_id: UUID) -> list[ChatMessage]:
        """Mark one session busy and return a defensive history copy."""

        with self._lock:
            state = self._require(session_id)
            if state.busy:
                raise SessionBusyError(str(session_id))
            state.busy = True
            state.updated_at = datetime.now(timezone.utc)
            return [message.model_copy(deep=True) for message in state.messages]

    def finish_turn(self, session_id: UUID, user_message: str, answer: str) -> None:
        with self._lock:
            state = self._require(session_id)
            state.messages.extend(
                [
                    ChatMessage(role=ChatRole.USER, content=user_message),
                    ChatMessage(role=ChatRole.ASSISTANT, content=answer),
                ]
            )
            self._trim_complete_turns(state)
            state.busy = False
            state.updated_at = datetime.now(timezone.utc)

    def abort_turn(self, session_id: UUID) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is not None:
                state.busy = False
                state.updated_at = datetime.now(timezone.utc)

    def history(self, session_id: UUID) -> list[ChatMessage]:
        with self._lock:
            state = self._require(session_id)
            return [message.model_copy(deep=True) for message in state.messages]

    def clear(self) -> int:
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            return count

    def _require(self, session_id: UUID) -> SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            raise SessionNotFoundError(str(session_id))
        return state

    def _trim_complete_turns(self, state: SessionState) -> None:
        while len(state.messages) > self.max_history_messages:
            del state.messages[:2]


def _snapshot(state: SessionState) -> SessionSnapshot:
    return SessionSnapshot(
        session_id=state.session_id,
        created_at=state.created_at,
        updated_at=state.updated_at,
        message_count=len(state.messages),
        busy=state.busy,
    )
