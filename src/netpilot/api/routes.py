"""NetPilot system API routes."""

from fastapi import APIRouter, Request

from netpilot.config import Settings
from netpilot.llm import TJUClient
from netpilot.models import HealthResponse


router = APIRouter()


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
