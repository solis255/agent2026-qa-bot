"""Structured Agent results and tool execution timeline models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from netpilot.llm import TokenUsage
from netpilot.tools.schemas import ToolResult


class AgentStatus(str, Enum):
    COMPLETED = "completed"
    MAX_TOOL_ROUNDS = "max_tool_rounds"
    LLM_ERROR = "llm_error"


class RegistryExecution(BaseModel):
    """Validated arguments paired with a safe tool result."""

    arguments: dict[str, Any] = Field(default_factory=dict)
    result: ToolResult[Any]


class AgentToolStep(BaseModel):
    """One correlated tool execution exposed to later timeline consumers."""

    round: int = Field(ge=1)
    tool_call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: ToolResult[Any]


class AgentResult(BaseModel):
    """Final one-shot diagnosis plus its bounded evidence trace."""

    answer: str = Field(min_length=1)
    status: AgentStatus
    tool_rounds: int = Field(ge=0)
    steps: list[AgentToolStep] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    llm_duration_ms: float = Field(default=0, ge=0)
