"""FastAPI entry point for TJU NetPilot."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from netpilot import __version__
from netpilot.agent import AgentOrchestrator, ToolRegistry
from netpilot.api.routes import router as api_router
from netpilot.config import Settings
from netpilot.llm import TJUClient
from netpilot.tools import build_network_tools


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"


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
    app.state.llm_client = TJUClient(app.state.settings)
    app.state.network_tools = build_network_tools(app.state.settings)
    app.state.tool_registry = ToolRegistry(app.state.network_tools)
    app.state.agent = AgentOrchestrator(
        app.state.llm_client,
        app.state.tool_registry,
        max_tool_rounds=app.state.settings.max_tool_rounds,
    )
    # Milestone 4 does not load a retriever. A later lifespan hook will set this
    # only after a usable knowledge index has been opened successfully.
    app.state.rag_ready = False

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
