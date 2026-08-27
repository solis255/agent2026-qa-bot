"""NetPilot health, conversation, and controlled demo scenario routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from netpilot.agent import (
    SessionBusyError,
    SessionCapacityError,
    SessionNotFoundError,
    SessionStore,
)
from netpilot.api.presenters import present_chat
from netpilot.config import MockScenario, Settings, ToolMode
from netpilot.llm import TJUClient
from netpilot.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ScenarioListResponse,
    ScenarioOption,
    ScenarioSwitchResponse,
    SessionResponse,
)
from netpilot.observability import log_event, reset_session_id, set_session_id


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
    log_event(
        logger,
        "agent_turn",
        success=True,
        llm_duration=round(result.llm_duration_ms, 2),
        tool_rounds=result.tool_rounds,
        status=str(getattr(result.status, "value", result.status)),
    )
    reset_session_id(session_token)
    return present_chat(payload.session_id, result)


@router.get("/scenarios", response_model=ScenarioListResponse, tags=["demo"])
def list_scenarios(request: Request) -> ScenarioListResponse:
    settings: Settings = request.app.state.settings
    if settings.tool_mode is not ToolMode.MOCK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local 模式不支持 Mock 场景。",
        )
    current = request.app.state.network_tools.provider.scenario
    return ScenarioListResponse(
        current=current,
        switch_enabled=settings.scenario_switch_enabled,
        scenarios=[
            ScenarioOption(name=name, label=label, description=description)
            for name, (label, description) in SCENARIO_DETAILS.items()
        ],
    )


@router.post(
    "/scenarios/{scenario}",
    response_model=ScenarioSwitchResponse,
    tags=["demo"],
)
def switch_scenario(
    scenario: MockScenario,
    request: Request,
) -> ScenarioSwitchResponse:
    settings: Settings = request.app.state.settings
    if settings.tool_mode is not ToolMode.MOCK:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local 模式不支持 Mock 场景切换。",
        )
    if not settings.scenario_switch_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock 场景切换未启用。",
        )
    with request.app.state.runtime_lock:
        current = request.app.state.network_tools.set_mock_scenario(scenario)
        cleared = _sessions(request).clear()
        snapshot = _sessions(request).create()
    return ScenarioSwitchResponse(
        current=current,
        session_id=snapshot.session_id,
        sessions_cleared=cleared,
    )


def _sessions(request: Request) -> SessionStore:
    return request.app.state.sessions
