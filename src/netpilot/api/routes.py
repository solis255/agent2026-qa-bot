"""NetPilot health, conversation, and controlled demo scenario routes."""

from __future__ import annotations

import logging
import re
from contextvars import copy_context
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from netpilot.agent import (
    SessionBusyError,
    SessionCapacityError,
    SessionNotFoundError,
    SessionStore,
)
from netpilot.api.presenters import present_chat
from netpilot.api.sse import iter_chat_sse
from netpilot.config import MockScenario, Settings, ToolMode
from netpilot.llm import TJUClient
from netpilot.history import (
    DiagnosisCursorError,
    DiagnosisRepository,
    DiagnosisRecordNotFoundError,
    DiagnosisStorageError,
)
from netpilot.models import (
    ChatRequest,
    ChatResponse,
    CustomScenarioCreateRequest,
    CustomScenarioDeleteResponse,
    DiagnosisHistoryResponse,
    DiagnosisReportView,
    DiagnosisRecordView,
    HealthResponse,
    ScenarioListResponse,
    ScenarioOption,
    ScenarioSwitchResponse,
    SessionResponse,
)
from netpilot.observability import log_event, reset_session_id, set_session_id
from netpilot.reports import (
    DiagnosisReportTooLargeError,
    build_diagnosis_report,
    export_diagnosis_report,
)
from netpilot.tools.custom_scenarios import (
    CustomScenarioExistsError,
    CustomScenarioLimitError,
    CustomScenarioNotFoundError,
)


logger = logging.getLogger(__name__)
router = APIRouter()

SCENARIO_DETAILS = {
    MockScenario.HEALTHY: ("网络正常", "各项基础网络检查均正常"),
    MockScenario.DNS_FAILURE: ("DNS 故障", "公网 IP 可达，但域名解析失败"),
    MockScenario.GATEWAY_UNREACHABLE: ("网关不可达", "本地接入或默认网关异常"),
    MockScenario.TCP_SSH_BLOCKED: ("SSH 端口受阻", "主机可达，但 TCP 22 端口不可连接"),
    MockScenario.HTTP_FAILURE: ("HTTP 访问失败", "网络和 443 端口正常，但 HTTP 层失败"),
    MockScenario.PARTIAL_CONNECTIVITY: ("部分连通", "部分目标或协议可用，需进一步定位"),
}


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    """Report configuration and component readiness without leaking secrets."""

    settings: Settings = request.app.state.settings
    llm_client: TJUClient = request.app.state.llm_client
    return HealthResponse(
        llm_configured=llm_client.configured,
        tool_mode=settings.tool_mode,
        rag_ready=bool(request.app.state.rag_ready),
        history_ready=bool(request.app.state.history_ready),
    )


@router.post(
    "/session",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["chat"],
)
def create_session(request: Request) -> SessionResponse:
    try:
        snapshot = _sessions(request).create()
    except SessionCapacityError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="会话容量已满，请稍后重试。",
        ) from exc
    return SessionResponse(
        session_id=snapshot.session_id,
        created_at=snapshot.created_at,
    )


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Run one bounded Agent turn and append only text history to the session."""

    llm_client: TJUClient = request.app.state.llm_client
    if not llm_client.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TJU LLM 未配置，请先在服务端设置 TJU_API_KEY。",
        )
    session_token = set_session_id(payload.session_id)
    sessions = _sessions(request)
    try:
        history = sessions.begin_turn(payload.session_id)
    except SessionNotFoundError as exc:
        reset_session_id(session_token)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或已失效，请新建会话。",
        ) from exc
    except SessionBusyError as exc:
        reset_session_id(session_token)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前会话正在诊断，请等待本次请求完成。",
        ) from exc

    try:
        with request.app.state.runtime_lock:
            result = request.app.state.agent.run(payload.message, history=history)
        sessions.finish_turn(payload.session_id, payload.message, result.answer)
    except Exception as exc:
        sessions.abort_turn(payload.session_id)
        log_event(
            logger,
            "agent_turn",
            level=logging.WARNING,
            success=False,
            error_type=type(exc).__name__,
        )
        reset_session_id(session_token)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="诊断请求处理失败，请稍后重试。",
        ) from exc
    response = present_chat(payload.session_id, result)
    repository = _diagnoses(request)
    if repository is not None:
        try:
            record = repository.save(payload.message, response)
            response = response.model_copy(update={"record_id": record.record_id})
        except DiagnosisStorageError:
            log_event(
                logger,
                "diagnosis_history_write",
                level=logging.WARNING,
                success=False,
                error_type="diagnosis_storage_error",
            )
    log_event(
        logger,
        "agent_turn",
        success=True,
        llm_duration=round(result.llm_duration_ms, 2),
        tool_rounds=result.tool_rounds,
        status=str(getattr(result.status, "value", result.status)),
    )
    reset_session_id(session_token)
    return response


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    tags=["chat"],
)
def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Run one Agent turn and emit a versioned JSON SSE event sequence."""

    llm_client: TJUClient = request.app.state.llm_client
    if not llm_client.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TJU LLM 未配置，请先在服务端设置 TJU_API_KEY。",
        )
    sessions = _sessions(request)
    try:
        history = sessions.begin_turn(payload.session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或已失效，请新建会话。",
        ) from exc
    except SessionBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前会话正在诊断，请等待本次请求完成。",
        ) from exc

    session_token = set_session_id(payload.session_id)
    stream_context = copy_context()
    reset_session_id(session_token)

    def run_turn() -> ChatResponse:
        try:
            with request.app.state.runtime_lock:
                result = request.app.state.agent.run(payload.message, history=history)
            sessions.finish_turn(payload.session_id, payload.message, result.answer)
            response = present_chat(payload.session_id, result)
            repository = _diagnoses(request)
            if repository is not None:
                try:
                    record = repository.save(payload.message, response)
                    response = response.model_copy(update={"record_id": record.record_id})
                except DiagnosisStorageError:
                    log_event(
                        logger,
                        "diagnosis_history_write",
                        level=logging.WARNING,
                        success=False,
                        error_type="diagnosis_storage_error",
                    )
            log_event(
                logger,
                "agent_turn_stream",
                success=True,
                llm_duration=round(result.llm_duration_ms, 2),
                tool_rounds=result.tool_rounds,
                status=str(getattr(result.status, "value", result.status)),
            )
            return response
        except Exception as exc:
            sessions.abort_turn(payload.session_id)
            log_event(
                logger,
                "agent_turn_stream",
                level=logging.WARNING,
                success=False,
                error_type=type(exc).__name__,
            )
            raise

    settings: Settings = request.app.state.settings
    return StreamingResponse(
        iter_chat_sse(
            payload.session_id,
            run_turn,
            chunk_chars=settings.sse_chunk_chars,
            heartbeat_seconds=settings.sse_heartbeat_seconds,
            context=stream_context,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/diagnoses",
    response_model=DiagnosisHistoryResponse,
    tags=["history"],
)
def list_diagnoses(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    session_id: UUID | None = None,
) -> DiagnosisHistoryResponse:
    repository = _require_diagnoses(request)
    try:
        return repository.list(
            limit=limit,
            cursor=cursor,
            session_id=session_id,
        )
    except DiagnosisCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="历史记录游标不合法。",
        ) from exc
    except DiagnosisStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="诊断历史暂时不可用。",
        ) from exc


@router.get(
    "/diagnoses/{record_id}",
    response_model=DiagnosisRecordView,
    tags=["history"],
)
def get_diagnosis(record_id: UUID, request: Request) -> DiagnosisRecordView:
    return _get_diagnosis_record(request, record_id)


@router.get(
    "/diagnoses/{record_id}/report",
    response_model=DiagnosisReportView,
    tags=["reports"],
)
def get_diagnosis_report(
    record_id: UUID,
    request: Request,
) -> DiagnosisReportView:
    record = _get_diagnosis_record(request, record_id)
    return build_diagnosis_report(record)


@router.get(
    "/diagnoses/{record_id}/export",
    response_class=Response,
    tags=["reports"],
)
def export_diagnosis(
    record_id: UUID,
    request: Request,
    report_format: Literal["markdown", "json"] = Query(alias="format"),
) -> Response:
    record = _get_diagnosis_record(request, record_id)
    report = build_diagnosis_report(record)
    try:
        artifact = export_diagnosis_report(
            report,
            report_format,
            max_bytes=request.app.state.settings.diagnosis_report_max_bytes,
        )
    except DiagnosisReportTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail="诊断报告超过允许的导出大小。",
        ) from exc
    log_event(
        logger,
        "diagnosis_report_export",
        record_id=str(record_id),
        report_format=report_format,
        report_bytes=len(artifact.content),
        success=True,
    )
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/scenarios", response_model=ScenarioListResponse, tags=["demo"])
def list_scenarios(request: Request) -> ScenarioListResponse:
    settings: Settings = request.app.state.settings
    if settings.tool_mode is not ToolMode.MOCK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local 模式不支持 Mock 场景。",
        )
    provider = request.app.state.network_tools.provider
    current = provider.scenario_name
    custom_scenarios = request.app.state.network_tools.list_custom_scenarios()
    return ScenarioListResponse(
        current=current,
        switch_enabled=settings.scenario_switch_enabled,
        custom_count=len(custom_scenarios),
        custom_limit=provider.max_custom_scenarios,
        scenarios=[
            ScenarioOption(
                name=name.value,
                label=label,
                description=description,
                kind="built_in",
            )
            for name, (label, description) in SCENARIO_DETAILS.items()
        ]
        + [
            ScenarioOption(
                name=scenario.name,
                label=scenario.label,
                description=scenario.description,
                kind="custom",
                behavior=scenario.behavior,
            )
            for scenario in custom_scenarios
        ],
    )


@router.post(
    "/scenarios/custom",
    response_model=ScenarioOption,
    status_code=status.HTTP_201_CREATED,
    tags=["demo"],
)
def create_custom_scenario(
    payload: CustomScenarioCreateRequest,
    request: Request,
) -> ScenarioOption:
    _require_custom_scenario_write(request)
    try:
        with request.app.state.runtime_lock:
            created = request.app.state.network_tools.add_custom_scenario(payload)
    except CustomScenarioExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except CustomScenarioLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return ScenarioOption(
        name=created.name,
        label=created.label,
        description=created.description,
        kind="custom",
        behavior=created.behavior,
    )


@router.delete(
    "/scenarios/custom/{scenario}",
    response_model=CustomScenarioDeleteResponse,
    tags=["demo"],
)
def delete_custom_scenario(
    scenario: str,
    request: Request,
) -> CustomScenarioDeleteResponse:
    _require_custom_scenario_write(request)
    _validate_scenario_name(scenario)
    try:
        with request.app.state.runtime_lock:
            was_active = request.app.state.network_tools.delete_custom_scenario(scenario)
            cleared = 0
            session_id = None
            if was_active:
                cleared = _sessions(request).clear()
                session_id = _sessions(request).create().session_id
            current = request.app.state.network_tools.provider.scenario_name
    except CustomScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="自定义 Mock 场景不存在。",
        ) from exc
    return CustomScenarioDeleteResponse(
        deleted=scenario,
        current=current,
        session_id=session_id,
        sessions_cleared=cleared,
    )


@router.post(
    "/scenarios/{scenario}",
    response_model=ScenarioSwitchResponse,
    tags=["demo"],
)
def switch_scenario(
    scenario: str,
    request: Request,
) -> ScenarioSwitchResponse:
    settings: Settings = request.app.state.settings
    if settings.tool_mode is not ToolMode.MOCK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local 模式不支持 Mock 场景切换。",
        )
    _validate_scenario_name(scenario)
    known_scenarios = {item.value for item in MockScenario}
    known_scenarios.update(
        item.name for item in request.app.state.network_tools.list_custom_scenarios()
    )
    if scenario not in known_scenarios:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mock 场景不存在。",
        )
    if not settings.scenario_switch_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock 场景切换未启用。",
        )
    try:
        with request.app.state.runtime_lock:
            current = request.app.state.network_tools.set_mock_scenario(scenario)
            cleared = _sessions(request).clear()
            snapshot = _sessions(request).create()
    except CustomScenarioNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mock 场景不存在。",
        ) from exc
    current_name = current.value if isinstance(current, MockScenario) else current
    return ScenarioSwitchResponse(
        current=current_name,
        session_id=snapshot.session_id,
        sessions_cleared=cleared,
    )


def _require_custom_scenario_write(request: Request) -> None:
    settings: Settings = request.app.state.settings
    if settings.tool_mode is not ToolMode.MOCK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local 模式不支持自定义 Mock 场景。",
        )
    if not settings.scenario_switch_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock 场景切换未启用。",
        )


def _validate_scenario_name(value: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,31}", value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mock 场景名称不合法。",
        )


def _sessions(request: Request) -> SessionStore:
    return request.app.state.sessions


def _diagnoses(request: Request) -> DiagnosisRepository | None:
    return request.app.state.diagnosis_repository


def _require_diagnoses(request: Request) -> DiagnosisRepository:
    repository = _diagnoses(request)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="诊断历史未启用或暂时不可用。",
        )
    return repository


def _get_diagnosis_record(
    request: Request,
    record_id: UUID,
) -> DiagnosisRecordView:
    repository = _require_diagnoses(request)
    try:
        return repository.get(record_id)
    except DiagnosisRecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="诊断记录不存在。",
        ) from exc
    except DiagnosisStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="诊断历史暂时不可用。",
        ) from exc
