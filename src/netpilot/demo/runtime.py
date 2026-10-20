"""Demo-owned runtimes. No global provider mutation, real probes or DB state fabrication."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from time import perf_counter
from uuid import UUID

from netpilot.agent import AgentOrchestrator, SessionStore, ToolRegistry
from netpilot.agent.session import SessionNotFoundError, SessionBusyError, SessionCapacityError
from netpilot.client_snapshot.validation import parse_snapshot
from netpilot.tools.schemas import ToolResult, ToolError, ToolErrorCode
from .scenarios import SCENARIOS

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "demo"


class FixtureOnlyTools:
    """Local-scope registry contract with no host/network implementation behind it."""
    provider_name = "local"

    def __init__(self):
        self.handler_calls = 0

    def __getattr__(self, name):
        if name not in {"get_network_info", "dns_lookup", "ping_host", "tcp_check", "http_check", "traceroute"}:
            raise AttributeError(name)
        def blocked(*args, **kwargs):
            self.handler_calls += 1
            return ToolResult(success=False, tool=name, summary="演示只接受客户端快照，不执行主机网络探测。", duration_ms=0,
                              error=ToolError(code=ToolErrorCode.SECURITY_BLOCKED, message="Host probing disabled in fixture runtime"))
        return blocked


class DemoLLMMetrics:
    """Observe real client calls, with no changes to messages or responses."""
    def __init__(self, client):
        self.client = client
        self.calls = 0
        self.total_tokens = 0
        self.duration_ms = 0.0

    def chat(self, *args, **kwargs):
        self.calls += 1
        started = perf_counter()
        try:
            result = self.client.chat(*args, **kwargs)
            self.total_tokens += result.usage.total_tokens
            return result
        finally:
            self.duration_ms += (perf_counter() - started) * 1000


@dataclass
class DemoRuntime:
    owner: UUID
    session_id: UUID
    scenario_id: str
    sessions: SessionStore
    tools: FixtureOnlyTools
    registry: ToolRegistry
    agent: AgentOrchestrator
    llm_metrics: DemoLLMMetrics
    loaded: dict = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)
    data_source: str = "fixture"


class DemoManager:
    def __init__(self, settings, llm):
        self.settings = settings
        self.llm = llm
        self._runtimes = {}
        self._lock = RLock()

    def lookup(self, sid):
        with self._lock:
            return self._runtimes.get(sid)

    def require(self, sid, owner):
        runtime = self.lookup(sid)
        if runtime is None or runtime.owner != owner: raise SessionNotFoundError("demo_not_found")
        return runtime

    def create(self, owner, scenario_id, *, replacing=None):
        scenario = SCENARIOS[scenario_id]
        with self._lock:
            old = self.require(replacing, owner) if replacing else None
            if old and old.sessions.get(replacing, owner).busy: raise SessionBusyError("demo_busy")
            if not old and len(self._runtimes) >= self.settings.max_sessions: raise SessionCapacityError("demo_capacity")
            store = SessionStore(provider_kind="local", environment_client_mode="remote_browser",
                reasoning_trace_enabled=self.settings.reasoning_trace_enabled, reasoning_trace_max_steps=self.settings.reasoning_trace_max_steps,
                verification_max_cycles=self.settings.verification_max_cycles, resolution_escalate_after_no_improvement=self.settings.resolution_escalate_after_no_improvement,
                resolution_max_transitions=self.settings.resolution_max_transitions, escalation_max_packages=self.settings.escalation_max_packages,
                escalation_max_evidence_items=self.settings.escalation_max_evidence_items, escalation_mask_private_ip=self.settings.escalation_mask_private_ip)
            sid = store.create(owner, is_demo=True, demo_scenario_id=scenario_id).session_id
            store.update_environment(sid, owner, scenario.environment_fixture.model_dump(), source="user")
            tools = FixtureOnlyTools()
            registry = ToolRegistry(tools)
            monitor = DemoLLMMetrics(self.llm)
            agent = AgentOrchestrator(monitor, registry, max_tool_rounds=self.settings.max_tool_rounds,
                reasoning_trace_enabled=self.settings.reasoning_trace_enabled, reasoning_trace_max_steps=self.settings.reasoning_trace_max_steps,
                remediation_max_steps=self.settings.remediation_max_steps)
            runtime = DemoRuntime(owner, sid, scenario_id, store, tools, registry, agent, monitor)
            self._runtimes[sid] = runtime
            if old: del self._runtimes[replacing]
            return runtime

    def fixture(self, runtime, fixture_id):
        allowed = SCENARIOS[runtime.scenario_id].snapshot_fixtures
        if fixture_id not in allowed: raise KeyError("fixture_not_in_scenario")
        if fixture_id in runtime.loaded: return runtime.loaded[fixture_id]
        index = allowed.index(fixture_id)
        if any(key not in runtime.loaded for key in allowed[:index]): raise ValueError("load_previous_fixture_first")
        value = json.loads((FIXTURE_ROOT / (fixture_id + ".json")).read_text(encoding="utf-8"))
        # Only capture time is rebased. The archived observations remain deterministic.
        value["generated_at"] = datetime.now(timezone.utc).isoformat()
        raw = json.dumps(value, ensure_ascii=False).encode()
        return parse_snapshot(raw, self.settings.client_snapshot_max_bytes)


def runtime_for(request, sid):
    manager = getattr(request.app.state, "demo_manager", None)
    return manager.lookup(sid) if manager else None


def store_for(request, sid):
    runtime = runtime_for(request, sid)
    return runtime.sessions if runtime else request.app.state.sessions
