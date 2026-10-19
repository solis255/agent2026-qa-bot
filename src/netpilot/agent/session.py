"""Thread-safe in-memory conversation sessions for the Web demo."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any
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
from netpilot.agent.reasoning_trace import merge_reasoning_trace
from netpilot.client_snapshot.schemas import refresh_summary
from netpilot.llm import ChatMessage, ChatRole
from netpilot.environment import ClientMode, EnvironmentProfile, EnvironmentSource, initial_environment, merge_environment
from netpilot.diagnostic_target import DiagnosticTarget, ProviderKind, derive_diagnostic_target, merge_diagnostic_target, user_target, binding_for


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
    message_targets: list[tuple[str, int]] = field(default_factory=list)
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
        reasoning_trace_max_steps: int = 50,
        reasoning_trace_enabled: bool = True,
        environment_client_mode: ClientMode = "unknown",
        provider_kind: ProviderKind = "unavailable",
        verification_max_cycles: int = 10,
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
        self.reasoning_trace_max_steps = reasoning_trace_max_steps
        self.reasoning_trace_enabled = reasoning_trace_enabled
        self.environment_client_mode = environment_client_mode
        self.provider_kind = provider_kind
        self.verification_max_cycles = verification_max_cycles
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
            environment_profile=initial_environment(self.environment_client_mode),
        )
        state.task_state.diagnostic_target = derive_diagnostic_target(state.task_state.environment_profile, self.provider_kind)
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
            target = _task_state(state).diagnostic_target
            identity = (target.subject, target.target_version)
            return [message.model_copy(deep=True) for message, recorded in zip(state.messages, state.message_targets) if recorded == identity]

    def finish_turn(
        self,
        session_id: UUID,
        user_message: str,
        answer: str,
        *,
        result: AgentResult | None = None,
        after_finish: Callable[[], Any] | None = None,
    ) -> Any:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                raise SessionNotFoundError(str(session_id))
            task_state = _task_state(state)
            if result is not None and result.diagnostic_target is not None:
                task_state.set_target(result.diagnostic_target)
            target = task_state.diagnostic_target
            state.message_targets.extend([(target.subject, target.target_version)] * 2)
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
                if result.environment_profile is not None:
                    task_state.environment_profile = result.environment_profile.model_copy(deep=True)
                for item in result.reasoning_trace:
                    if item.title == "确认用户环境":
                        task_state.last_environment_trace_summary = item.summary
                    if item.title in {"确认诊断对象", "切换诊断对象"}:
                        task_state.last_target_trace_version = target.target_version
                    if item.title == "限制不适用的检测":
                        task_state.last_target_limit_version = target.target_version
                task_state.reasoning_trace = merge_reasoning_trace(
                    task_state.reasoning_trace,
                    [step if step.event_origin != "agent" else step.model_copy(update={"turn_index": task_state.turn_index, "task_version": task_state.task_version}) for step in result.reasoning_trace],
                    self.reasoning_trace_max_steps,
                )
                for step in result.steps:
                    if step.target_subject == "unknown" and target.subject != "unknown":
                        scope = "target_neutral" if step.tool_name == "knowledge_search" else "mock_target" if target.execution_context == "mock_provider" else "execution_host"
                        step = step.model_copy(update={**binding_for(target, scope), "tool_signature":None})
                    record = evidence_from_step(
                        step,
                        turn_index=task_state.turn_index,
                        task_version=task_state.task_version,
                    )
                    task_state.evidence.append(record)
                    task_state.executed_tool_signatures.add(record.tool_signature)
                if result.remediation_updated:
                    # Install new baseline pins before trimming; otherwise an
                    # evidence-full Session could remove a just-frozen record.
                    task_state.verification_cycles = [c.model_copy(deep=True) for c in result.verification_cycles][-self.verification_max_cycles:]
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
                if result.turn_intent in {TurnIntent.DIAGNOSE,TurnIntent.STATE_CHANGED,TurnIntent.CLARIFY}:
                    task_state.remediation_symptom = user_message
                if result.remediation_updated:
                    task_state.verification_sequence = max(task_state.verification_sequence,max((c.verification_sequence for c in task_state.verification_cycles),default=0))
                    task_state.remediation_plan = result.remediation_plan.model_copy(deep=True) if result.remediation_plan else None
                    task_state.remediation_plan_history = [item.model_copy(deep=True) for item in result.remediation_plan_history]
                    if result.remediation_readiness: task_state.remediation_readiness = result.remediation_readiness
                    task_state.remediation_plan_version = max(task_state.remediation_plan_version,result.remediation_plan.plan_version if result.remediation_plan else 0)
            # Persist under this lock, so a PATCH cannot race a completed Turn.
            response = after_finish() if after_finish is not None else None
            task_state.pending_snapshot_trace.clear()
            task_state.pending_remediation_trace.clear()
            state.busy = False
            state.updated_at = datetime.now(timezone.utc)
            return response

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
            task = _task_state(state).model_copy(deep=True)
            task.client_snapshot_summary = refresh_summary(task.client_snapshot_summary)
            now = datetime.now(timezone.utc)
            for item in task.evidence:
                if item.expires_at:
                    item.stale = now > item.expires_at
            from netpilot.remediation.service import invalidate
            invalidate(task)
            from netpilot.verification.service import invalidate_cycles
            invalidate_cycles(task)
            return task

    def remediation(self, session_id, owner_user_id, *, generate=False, step_id=None, feedback=None, max_steps=5, persist=None):
        """Owner-scoped atomic plan/feedback update, without adding a chat Turn."""
        from netpilot.remediation.service import ensure_plan, update_step
        with self._lock:
            state = self._require(session_id,owner_user_id)
            if state.busy: raise SessionBusyError(str(session_id))
            original = _task_state(state)
            draft = self.task_state(session_id,owner_user_id)
            events = []
            if generate:
                _,events = ensure_plan(draft,max_steps=max_steps,trace_enabled=self.reasoning_trace_enabled,trace_limit=self.reasoning_trace_max_steps)
            if feedback is not None:
                events = update_step(draft,step_id,feedback,trace_enabled=self.reasoning_trace_enabled,trace_limit=self.reasoning_trace_max_steps)
            if draft.model_dump() != original.model_dump():
                draft.verification_cycles = draft.verification_cycles[-self.verification_max_cycles:]
                persisted = persist(draft) if persist else False
                if not persisted: draft.pending_remediation_trace.extend(events)
                state.task_state = draft
                state.updated_at = datetime.now(timezone.utc)
            return draft.model_copy(deep=True),events

    def verification(self, session_id, owner_user_id, *, action="get", cycle_id=None, observation=None, reverify=False, registry=None, persist=None):
        """Owner-scoped draft -> persistence -> memory commit; no fake chat Turn."""
        from netpilot.verification.service import ensure_baseline, activate, host_refresh, invalidate_cycles, emit
        from netpilot.verification.evaluator import VerificationEvaluator
        with self._lock:
            state = self._require(session_id,owner_user_id)
            if state.busy: raise SessionBusyError(str(session_id))
            original = _task_state(state)
            draft = self.task_state(session_id,owner_user_id)
            invalidate_cycles(draft)
            events = []
            cycle = draft.verification_cycles[-1] if draft.verification_cycles else None
            if action == "create":
                cycle,events = ensure_baseline(draft,reverify=reverify,max_cycles=self.verification_max_cycles)
            if cycle_id is not None and (cycle is None or cycle.verification_id != cycle_id): raise KeyError("cycle_not_current")
            if action in {"start","observation"}:
                if not cycle or cycle.status == "superseded": raise ValueError("cycle_superseded")
                if (cycle.target_subject,cycle.target_version) != (draft.diagnostic_target.subject,draft.diagnostic_target.target_version) or draft.task_version not in {cycle.baseline.task_version,cycle.after_task_version}: raise ValueError("cycle_not_current_scope")
            if action == "start":
                if cycle.status == "baseline_ready" and not any(s.status == "completed" for s in draft.remediation_plan.steps): raise ValueError("complete_manual_step_first")
                events.extend(activate(draft,cycle))
                if cycle.target_subject == "netpilot_host": events.extend(host_refresh(draft,cycle,registry))
            if action == "observation":
                if cycle.user_observation is None or cycle.user_observation.model_dump(exclude={"observed_at"}) != observation.model_dump(exclude={"observed_at"}):
                    cycle.user_observation = observation
                    if cycle.status != "failed":
                        cycle.result,cycle.result_summary = VerificationEvaluator().evaluate(cycle)
                        if cycle.after: cycle.status = "inconclusive" if cycle.result == "inconclusive" else "completed"
                    cycle.updated_at = datetime.now(timezone.utc)
                    events.append(emit(draft,"记录用户验证反馈","用户主观症状反馈已单独保存，不冒充客观网络检测；冲突会明确保留。",cycle,"observation"))
            if not self.reasoning_trace_enabled:
                draft.reasoning_trace = [e for e in draft.reasoning_trace if e not in events]; events = []
            if draft.model_dump() != original.model_dump():
                persisted = persist(draft) if persist else False
                if not persisted: draft.pending_remediation_trace.extend(events)
                state.task_state = draft; state.updated_at = datetime.now(timezone.utc)
            return draft.model_copy(deep=True),events

    def import_client_snapshot(self, session_id, owner_user_id, snapshot, digest, *, freshness_minutes=15, persist=None):
        """Atomic owner-scoped import. A snapshot is not an Agent Turn/Tool Call."""
        from netpilot.client_snapshot.service import normalize_snapshot
        with self._lock:
            state = self._require(session_id, owner_user_id)
            if state.busy:
                raise SessionBusyError(str(session_id))
            current = _task_state(state)
            target = current.diagnostic_target
            if target.subject != "user_client" or target.relationship_to_netpilot != "remote" or self.provider_kind == "mock":
                raise ValueError("snapshot_requires_remote_user_client")
            summary = current.client_snapshot_summary
            if summary and summary.snapshot_digest == digest and summary.target_version == target.target_version and summary.task_version == current.task_version:
                return self.task_state(session_id, owner_user_id), True, []
            draft = current.model_copy(deep=True)
            records, events = normalize_snapshot(snapshot, digest, draft, freshness_minutes=freshness_minutes, trace_enabled=self.reasoning_trace_enabled)
            # Preserve replaced snapshot observations for audit while bounding memory.
            # Reserve some slots for actual Tool evidence; reject rather than lose audit.
            if sum(item.evidence_origin == "client_snapshot" for item in draft.evidence) > max(1, self.max_evidence_records * 4 // 5):
                raise SessionCapacityError("snapshot_archive_full")
            draft.reasoning_trace = merge_reasoning_trace([], draft.reasoning_trace, self.reasoning_trace_max_steps)
            persisted = persist(draft) if persist is not None else False
            if not persisted:
                draft.pending_snapshot_trace.extend(events)
            state.task_state = draft
            self._trim_evidence(draft)
            state.updated_at = datetime.now(timezone.utc)
            return self.task_state(session_id, owner_user_id), False, events

    def update_environment(
        self, session_id: UUID, owner_user_id: UUID, values: dict, *,
        source: EnvironmentSource,
        persist: Callable[[EnvironmentProfile], None] | None = None,
    ) -> EnvironmentProfile:
        """Merge current context without invalidating Evidence or creating a Turn."""
        with self._lock:
            state = self._require(session_id, owner_user_id)
            if state.busy:
                raise SessionBusyError(str(session_id))
            task = _task_state(state)
            profile = merge_environment(task.environment_profile, values, source=source)
            if persist is not None:
                persist(profile)
            task.environment_profile = profile
            from netpilot.remediation.service import invalidate
            invalidate(task)
            state.updated_at = datetime.now(timezone.utc)
            return profile.model_copy(deep=True)

    def advance_task_version(self, session_id: UUID, owner_user_id: UUID) -> int:
        """Start a fresh evidence version while preserving old observations."""

        with self._lock:
            state = self._require(session_id, owner_user_id)
            task_state = _task_state(state)
            task_state.advance_version()
            state.updated_at = datetime.now(timezone.utc)
            return task_state.task_version

    def update_diagnostic_target(self, session_id: UUID, owner_user_id: UUID, subject, *, persist=None) -> DiagnosticTarget:
        with self._lock:
            state = self._require(session_id, owner_user_id)
            if state.busy:
                raise SessionBusyError(str(session_id))
            if self.provider_kind == "mock":
                raise ValueError("Mock 模拟终端由系统管理，不可切换为真实设备。")
            task = _task_state(state)
            target = merge_diagnostic_target(task.diagnostic_target, user_target(subject, task.environment_profile, self.provider_kind), self.provider_kind)
            if persist is not None:
                persist(target)
            task.set_target(target)
            state.updated_at = datetime.now(timezone.utc)
            return target.model_copy(deep=True)

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
            del state.message_targets[:2]

    def _trim_evidence(self, task_state: SessionTaskState) -> None:
        overflow = len(task_state.evidence) - self.max_evidence_records
        if overflow > 0:
            pinned = {eid for c in task_state.verification_cycles for evidence_set in [c.baseline,c.after] if evidence_set for eid in evidence_set.evidence_ids}
            removable = [item.evidence_id for item in task_state.evidence if item.evidence_origin != "client_snapshot" and item.evidence_id not in pinned][:overflow]
            task_state.evidence = [item for item in task_state.evidence if item.evidence_id not in removable]
        task_state.executed_tool_signatures = {record.tool_signature for record in task_state.reusable_evidence() if record.evidence_origin in {"tool", "knowledge"}}


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
