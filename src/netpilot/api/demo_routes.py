"""Authenticated demo preparation only. Outcomes are computed by regular services."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from netpilot.api.remediation_routes import CurrentUser
from netpilot.agent.session import SessionNotFoundError, SessionBusyError, SessionCapacityError
from netpilot.client_snapshot.validation import SnapshotValidationError
from netpilot.history import DiagnosisStorageError
from netpilot.demo.models import DemoSessionRequest
from netpilot.demo.scenarios import SCENARIOS


def enabled(request: Request):
    if not request.app.state.settings.demo_mode: raise HTTPException(404, "演示 API 未启用。")


router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Depends(enabled)])


def owned(request, sid, owner):
    try: return request.app.state.demo_manager.require(sid, owner)
    except SessionNotFoundError as exc: raise HTTPException(404, "演示会话不存在。") from exc


def session_view(request, runtime, user):
    from netpilot.api.routes import get_session
    return get_session(runtime.session_id, request, user, Response())


def create(request, user, scenario_id, replacing=None):
    if scenario_id not in SCENARIOS: raise HTTPException(404, "演示场景不存在。")
    try:
        runtime = request.app.state.demo_manager.create(user.id, scenario_id, replacing=replacing)
        return session_view(request, runtime, user)
    except SessionNotFoundError as exc: raise HTTPException(404, "演示会话不存在。") from exc
    except SessionBusyError as exc: raise HTTPException(409, "演示正在处理，请稍后重置。") from exc
    except SessionCapacityError as exc: raise HTTPException(503, "演示会话容量已满。") from exc


@router.get("/scenarios")
def scenarios(user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"notice": "DEMO / Mock — 网络状态来自 Fixture，不代表现场真实网络。",
            "scenarios": [s.model_dump(mode="json") for s in SCENARIOS.values()]}


@router.post("/session", status_code=201)
def new_session(payload: DemoSessionRequest, request: Request, user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return create(request, user, payload.scenario_id)


@router.post("/session/{session_id}/scenario/{scenario_id}", status_code=201)
def select(session_id: UUID, scenario_id: str, request: Request, user: CurrentUser):
    owned(request, session_id, user.id)
    return create(request, user, scenario_id, replacing=session_id)


@router.post("/session/{session_id}/reset", status_code=201)
def reset(session_id: UUID, request: Request, user: CurrentUser):
    runtime = owned(request, session_id, user.id)
    return create(request, user, runtime.scenario_id, replacing=session_id)


@router.post("/session/{session_id}/load-snapshot/{fixture_id}")
def load_snapshot(session_id: UUID, fixture_id: str, request: Request, user: CurrentUser, response: Response):
    runtime = owned(request, session_id, user.id)
    manager = request.app.state.demo_manager
    response.headers["Cache-Control"] = "no-store"
    try:
        with runtime.lock:
            if fixture_id in runtime.loaded and fixture_id != next(reversed(runtime.loaded)):
                raise ValueError("reset_to_replay_old_capture")
            snapshot, digest = manager.fixture(runtime, fixture_id)
            def persist(task):
                repository = request.app.state.diagnosis_repository
                if repository is not None: return repository.update_client_snapshot(user.id, session_id, task)
                if request.app.state.settings.diagnosis_history_enabled: raise DiagnosisStorageError("history_unavailable")
                return False
            # Identical to a validated uploaded snapshot: no Evidence/state injection.
            task, duplicate, events = runtime.sessions.import_client_snapshot(session_id, user.id, snapshot, digest,
                freshness_minutes=request.app.state.settings.client_snapshot_freshness_minutes, persist=persist)
            runtime.loaded[fixture_id] = (snapshot, digest)
            runtime.data_source = "fixture"
            result = session_view(request, runtime, user).model_dump(mode="json")
            result.update(duplicate=duplicate, reasoning_trace=[e.model_dump(mode="json") for e in events], fixture_id=fixture_id)
            return result
    except KeyError as exc: raise HTTPException(404, "该场景没有此快照。") from exc
    except SnapshotValidationError as exc: raise HTTPException(422, "演示快照未通过正式校验。") from exc
    except ValueError as exc: raise HTTPException(409, "请按 Before / After 顺序操作；重放旧快照请重置当前演示。") from exc
    except SessionBusyError as exc: raise HTTPException(409, "会话正在诊断，请稍后加载快照。") from exc
    except DiagnosisStorageError as exc: raise HTTPException(503, "快照保存失败，当前演示保留。") from exc


@router.get("/session/{session_id}")
def status(session_id: UUID, request: Request, user: CurrentUser, response: Response):
    runtime = owned(request, session_id, user.id)
    task = runtime.sessions.task_state(session_id, user.id)
    response.headers["Cache-Control"] = "no-store"
    scenario = SCENARIOS[runtime.scenario_id]
    latest = task.verification_cycles[-1] if task.verification_cycles else None
    return {"is_demo": True, "session_id": str(session_id), "demo_scenario_id": runtime.scenario_id,
        "data_notice": "DEMO / 模拟数据", "data_source": runtime.data_source,
        "task_version": task.task_version, "target_version": task.diagnostic_target.target_version,
        "resolution": task.resolution.state, "latest_verification": latest.result if latest else None,
        "latest_verification_historical": bool(latest and (latest.after_task_version or latest.baseline.task_version) != task.task_version),
        "latest_plan_version": task.remediation_plan.plan_version if task.remediation_plan else None,
        "loaded_fixtures": list(runtime.loaded), "snapshot_fixtures": scenario.snapshot_fixtures,
        "host_handler_calls": runtime.tools.handler_calls,
        "metrics": {"llm_calls": runtime.llm_metrics.calls, "total_tokens": runtime.llm_metrics.total_tokens,
                    "llm_duration_ms": round(runtime.llm_metrics.duration_ms, 2), "tool_calls": len([e for e in task.evidence if e.evidence_origin == "tool"]), "rag_calls": 0,
                    "remediation_steps": len(task.remediation_plan.steps) if task.remediation_plan else 0,
                    "verification_cycles": len(task.verification_cycles), "resolution_transitions": len(task.resolution_transitions)},
        "recommended_input": scenario.recommended_input}
