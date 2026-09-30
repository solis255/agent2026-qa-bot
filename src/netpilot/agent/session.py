"""Thread-safe in-memory conversation sessions for the Web demo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4

from netpilot.agent.coverage import (
    assess_evidence_sufficiency,
    coverage_from_observations,
)
from netpilot.agent.hypotheses import track_hypotheses
from netpilot.agent.intent import TurnIntent
from netpilot.agent.schemas import AgentResult
from netpilot.agent.task_state import SessionTaskState, evidence_from_step
from netpilot.llm import ChatMessage, ChatRole


class SessionNotFoundError(KeyError):
    """Raised when a client references an unknown or cleared session."""


class SessionBusyError(RuntimeError):
    """Raised when a second request targets an active session."""


class SessionCapacityError(RuntimeError):
    """Raised when every bounded session slot is actively in use."""


@dataclass
class SessionState:
    session_id: UUID
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessage] = field(default_factory=list)
    task_state: SessionTaskState | None = None
    busy: bool = False


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: UUID
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime
    message_count: int
    evidence_count: int
    task_version: int
    turn_index: int
    busy: bool


class SessionStore:
    """Keep bounded user/assistant history without persisting credentials."""

    def __init__(
        self,
        *,
        max_history_messages: int = 20,
        max_sessions: int = 500,
        max_evidence_records: int = 200,
    ) -> None:
        if max_history_messages < 1:
            raise ValueError("max_history_messages must be at least 1")
        if max_sessions < 1:
            raise ValueError("max_sessions must be at least 1")
        if max_evidence_records < 1:
            raise ValueError("max_evidence_records must be at least 1")
        self.max_history_messages = max_history_messages
        self.max_sessions = max_sessions
        self.max_evidence_records = max_evidence_records
        self._sessions: dict[UUID, SessionState] = {}
        self._lock = RLock()

    def create(self, owner_user_id: UUID) -> SessionSnapshot:
        now = datetime.now(timezone.utc)
        state = SessionState(
            session_id=uuid4(), owner_user_id=owner_user_id,
            created_at=now, updated_at=now,
        )
        state.task_state = SessionTaskState(
            session_id=state.session_id,
            owner_user_id=owner_user_id,
        )
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                idle = [item for item in self._sessions.values() if not item.busy]
                if not idle:
                    raise SessionCapacityError("all session slots are busy")
                oldest = min(idle, key=lambda item: item.updated_at)
                del self._sessions[oldest.session_id]
            self._sessions[state.session_id] = state
        return _snapshot(state)

    def get(self, session_id: UUID, owner_user_id: UUID) -> SessionSnapshot:
        with self._lock:
            return _snapshot(self._require(session_id, owner_user_id))

    def begin_turn(self, session_id: UUID, owner_user_id: UUID) -> list[ChatMessage]:
        """Mark one session busy and return a defensive history copy."""

        with self._lock:
            state = self._require(session_id, owner_user_id)
            if state.busy:
                raise SessionBusyError(str(session_id))
            state.busy = True
            state.updated_at = datetime.now(timezone.utc)
            return [message.model_copy(deep=True) for message in state.messages]

    def finish_turn(
        self,
        session_id: UUID,
        user_message: str,
        answer: str,
        *,
        result: AgentResult | None = None,
    ) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                raise SessionNotFoundError(str(session_id))
            state.messages.extend(
                [
                    ChatMessage(role=ChatRole.USER, content=user_message),
                    ChatMessage(role=ChatRole.ASSISTANT, content=answer),
                ]
            )
            self._trim_complete_turns(state)
            task_state = _task_state(state)
            if result is not None and result.task_version_advanced:
                task_state.advance_version()
            task_state.turn_index += 1
            if result is not None:
                for step in result.steps:
                    record = evidence_from_step(
                        step,
                        turn_index=task_state.turn_index,
                        task_version=task_state.task_version,
                    )
                    task_state.evidence.append(record)
                    task_state.executed_tool_signatures.add(record.tool_signature)
                self._trim_evidence(task_state)
                if result.turn_intent is not None:
                    task_state.last_turn_intent = result.turn_intent.value
                if result.response_mode is not None:
                    task_state.last_response_mode = result.response_mode.value
                task_state.last_fallback_reason = (
                    result.fallback_reason.value
                    if result.fallback_reason is not None
                    else None
                )
                active_evidence = task_state.reusable_evidence()
                task_state.coverage = coverage_from_observations(
                    evidence=active_evidence,
                )
                task_state.hypotheses = track_hypotheses(
                    evidence=active_evidence,
                )
                task_state.last_evidence_sufficiency = assess_evidence_sufficiency(
                    user_message,
                    task_state.coverage,
                    diagnostic=result.turn_intent
                    in {TurnIntent.DIAGNOSE, TurnIntent.STATE_CHANGED},
                )
            state.busy = False
            state.updated_at = datetime.now(timezone.utc)

    def abort_turn(self, session_id: UUID) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is not None:
                state.busy = False
                state.updated_at = datetime.now(timezone.utc)

    def history(self, session_id: UUID, owner_user_id: UUID) -> list[ChatMessage]:
        with self._lock:
            state = self._require(session_id, owner_user_id)
            return [message.model_copy(deep=True) for message in state.messages]

    def task_state(
        self,
        session_id: UUID,
        owner_user_id: UUID,
    ) -> SessionTaskState:
        """Return a defensive copy of structured cross-turn task memory."""

        with self._lock:
            state = self._require(session_id, owner_user_id)
            return _task_state(state).model_copy(deep=True)

    def advance_task_version(self, session_id: UUID, owner_user_id: UUID) -> int:
        """Start a fresh evidence version while preserving old observations."""

        with self._lock:
            state = self._require(session_id, owner_user_id)
            task_state = _task_state(state)
            task_state.advance_version()
            state.updated_at = datetime.now(timezone.utc)
            return task_state.task_version

    def clear(self) -> int:
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            return count

    def _require(self, session_id: UUID, owner_user_id: UUID) -> SessionState:
        state = self._sessions.get(session_id)
        if state is None or state.owner_user_id != owner_user_id:
            raise SessionNotFoundError(str(session_id))
        return state

    def _trim_complete_turns(self, state: SessionState) -> None:
        while len(state.messages) > self.max_history_messages:
            del state.messages[:2]

    def _trim_evidence(self, task_state: SessionTaskState) -> None:
        overflow = len(task_state.evidence) - self.max_evidence_records
        if overflow > 0:
            del task_state.evidence[:overflow]
        task_state.executed_tool_signatures = {
            record.tool_signature
            for record in task_state.evidence
            if record.task_version == task_state.task_version
            and not record.superseded
        }


def _snapshot(state: SessionState) -> SessionSnapshot:
    task_state = _task_state(state)
    return SessionSnapshot(
        session_id=state.session_id,
        owner_user_id=state.owner_user_id,
        created_at=state.created_at,
        updated_at=state.updated_at,
        message_count=len(state.messages),
        evidence_count=len(task_state.evidence),
        task_version=task_state.task_version,
        turn_index=task_state.turn_index,
        busy=state.busy,
    )


def _task_state(state: SessionState) -> SessionTaskState:
    if state.task_state is None:
        state.task_state = SessionTaskState(
            session_id=state.session_id,
            owner_user_id=state.owner_user_id,
        )
    return state.task_state
