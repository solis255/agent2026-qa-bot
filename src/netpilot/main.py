"""FastAPI entry point for TJU NetPilot."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from threading import RLock
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from netpilot import __version__
from netpilot.agent import AgentOrchestrator, SessionStore, ToolRegistry
from netpilot.api.routes import router as api_router
from netpilot.config import Settings
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
    )
    app.state.rag_ready = app.state.retriever is not None
    app.state.diagnosis_repository = None
    if app.state.settings.diagnosis_history_enabled:
        try:
            app.state.diagnosis_repository = SQLiteDiagnosisRepository(
                app.state.settings.diagnosis_db_path,
                max_records=app.state.settings.diagnosis_max_records,
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
        max_history_messages=app.state.settings.max_history_messages,
        max_sessions=app.state.settings.max_sessions,
    )
    # The Mock provider is shared mutable demo state. Serialize Agent runs with
    # scenario changes so a diagnostic turn cannot observe two scenarios.
    app.state.runtime_lock = RLock()

    app.include_router(api_router, prefix="/api")
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
