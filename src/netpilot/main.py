"""FastAPI entry point for TJU NetPilot."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from threading import RLock
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from netpilot import __version__
from netpilot.agent import AgentOrchestrator, SessionStore, ToolRegistry
from netpilot.api.routes import router as api_router
from netpilot.api.auth_routes import router as auth_router
from netpilot.config import Settings, ToolMode
from netpilot.llm import TJUClient
from netpilot.history import DiagnosisStorageError, SQLiteDiagnosisRepository
from netpilot.observability import (
    configure_observability,
    log_event,
    request_logging_middleware,
)
from netpilot.rag import load_configured_retriever
from netpilot.tools import build_network_tools


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"
logger = logging.getLogger(__name__)


async def _validation_error_without_auth_secrets(
    request: Request, exc: RequestValidationError
) -> Response:
    """Do not echo rejected auth/environment values (especially secrets)."""

    details = [
        {"type": error["type"], "loc": error["loc"], "msg": "请求参数不符合要求。"}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


@asynccontextmanager
async def app_lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Release locally owned client transports when the application stops."""

    try:
        yield
    finally:
        llm_client = getattr(application.state, "llm_client", None)
        if llm_client is not None:
            llm_client.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application instance without contacting external services."""

    app = FastAPI(
        title="TJU NetPilot API",
        summary="天津大学校园网络智能诊断与服务 Agent",
        version=__version__,
        lifespan=app_lifespan,
    )
    app.state.settings = settings or Settings()
    from netpilot.privacy import PrivacyPolicy
    from netpilot.privacy.middleware import PrivacyMiddleware
    app.state.privacy_policy = PrivacyPolicy.from_settings(app.state.settings)
    app.add_middleware(PrivacyMiddleware, policy=app.state.privacy_policy)
    from netpilot.remediation.catalog import CATALOG
    from netpilot.remediation.safety import validate_catalog
    validate_catalog(CATALOG)
    app.add_exception_handler(
        RequestValidationError, _validation_error_without_auth_secrets
    )
    configure_observability(app.state.settings.log_level)
    app.middleware("http")(request_logging_middleware)
    app.state.llm_client = TJUClient(app.state.settings)
    app.state.network_tools = build_network_tools(app.state.settings)
    app.state.retriever = load_configured_retriever(app.state.settings)
    app.state.tool_registry = ToolRegistry(
        app.state.network_tools,
        app.state.retriever,
    )
    app.state.agent = AgentOrchestrator(
        app.state.llm_client,
        app.state.tool_registry,
        max_tool_rounds=app.state.settings.max_tool_rounds,
        max_rag_calls_per_turn=app.state.settings.max_rag_calls_per_turn,
        max_output_tokens=app.state.settings.llm_max_output_tokens,
        report_max_output_tokens=app.state.settings.llm_report_max_output_tokens,
        knowledge_max_output_tokens=app.state.settings.llm_knowledge_max_output_tokens,
        reasoning_trace_enabled=app.state.settings.reasoning_trace_enabled,
        reasoning_trace_max_steps=app.state.settings.reasoning_trace_max_steps,
        reasoning_summary_llm_enabled=app.state.settings.reasoning_summary_llm_enabled,
        remediation_max_steps=app.state.settings.remediation_max_steps,
    )
    app.state.rag_ready = app.state.retriever is not None
    app.state.diagnosis_repository = None
    if app.state.settings.diagnosis_history_enabled:
        try:
            app.state.diagnosis_repository = SQLiteDiagnosisRepository(
                app.state.settings.diagnosis_db_path,
                max_records=app.state.settings.diagnosis_max_records,
                reasoning_trace_max_steps=app.state.settings.reasoning_trace_max_steps,
            )
        except DiagnosisStorageError:
            log_event(
                logger,
                "diagnosis_history_init",
                level=logging.WARNING,
                success=False,
                error_type="diagnosis_storage_error",
            )
    app.state.history_ready = app.state.diagnosis_repository is not None
    app.state.sessions = SessionStore(
        resolution_max_transitions=app.state.settings.resolution_max_transitions,
        resolution_escalate_after_no_improvement=app.state.settings.resolution_escalate_after_no_improvement,
        escalation_max_evidence_items=app.state.settings.escalation_max_evidence_items,
        escalation_max_packages=app.state.settings.escalation_max_packages,
        escalation_mask_private_ip=app.state.settings.escalation_mask_private_ip,
        verification_max_cycles=app.state.settings.verification_max_cycles,
        max_history_messages=app.state.settings.max_history_messages,
        max_sessions=app.state.settings.max_sessions,
        environment_client_mode="mock" if app.state.settings.tool_mode == ToolMode.MOCK else "remote_browser",
        provider_kind=app.state.network_tools.provider_name,
        reasoning_trace_enabled=app.state.settings.reasoning_trace_enabled,
        reasoning_trace_max_steps=app.state.settings.reasoning_trace_max_steps,
    )
    # The Mock provider is shared mutable demo state. Serialize Agent runs with
    # scenario changes so a diagnostic turn cannot observe two scenarios.
    app.state.runtime_lock = RLock()
    app.state.auth_lock = RLock()
    app.state.auth_service = None
    from netpilot.demo.runtime import DemoManager
    app.state.demo_manager = DemoManager(app.state.settings, app.state.llm_client)

    from netpilot.api.remediation_routes import router as remediation_router
    app.include_router(remediation_router,prefix="/api")
    from netpilot.api.verification_routes import router as verification_router
    app.include_router(verification_router,prefix="/api")
    from netpilot.api.resolution_routes import router as resolution_router
    app.include_router(resolution_router,prefix="/api")
    from netpilot.api.escalation_routes import router as escalation_router
    app.include_router(escalation_router,prefix="/api")
    app.include_router(api_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    from netpilot.api.client_snapshot_routes import router as snapshot_router
    app.include_router(snapshot_router)
    from netpilot.api.demo_routes import router as demo_router
    app.include_router(demo_router, prefix="/api")
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()


def run() -> None:
    """Run the development server via ``python -m netpilot.main``."""

    import uvicorn

    settings: Settings = app.state.settings
    uvicorn.run(
        "netpilot.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run()
