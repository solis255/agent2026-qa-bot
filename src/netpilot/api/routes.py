"""Milestone 1 API routes."""

from fastapi import APIRouter, Request

from netpilot.config import Settings
from netpilot.models import HealthResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    """Report configuration and component readiness without leaking secrets."""

    settings: Settings = request.app.state.settings
    return HealthResponse(
        llm_configured=settings.llm_configured,
        tool_mode=settings.tool_mode,
        rag_ready=bool(request.app.state.rag_ready),
    )
