"""API schemas introduced by the NetPilot application."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from netpilot.config import ToolMode


class HealthResponse(BaseModel):
    """Public service-readiness state; deliberately contains no credentials."""

    model_config = ConfigDict(use_enum_values=True)

    status: Literal["ok"] = "ok"
    llm_configured: bool
    tool_mode: ToolMode
    rag_ready: bool
