"""Provider-neutral schemas for chat completions and native function calls."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatRole(str, Enum):
    """Roles supported by the OpenAI-compatible Chat Completions protocol."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FunctionCall(BaseModel):
    """JSON-encoded function request emitted by the model."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    arguments: str = Field(min_length=1, max_length=20_000)

    @field_validator("name", "arguments")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class ToolCall(BaseModel):
    """One native function tool call and its correlation identifier."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=256)
    type: Literal["function"] = "function"
    function: FunctionCall

    @field_validator("id")
    @classmethod
    def strip_tool_call_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tool call id must not be empty")
        return normalized


class ChatMessage(BaseModel):
    """Validated text, assistant-tool-call, or tool-result message."""

    model_config = ConfigDict(extra="forbid")

    role: ChatRole
    content: str | None = Field(default=None, max_length=20_000)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = Field(default=None, max_length=256)

    @field_validator("content", "tool_call_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_role_shape(self) -> "ChatMessage":
        if self.role in {ChatRole.SYSTEM, ChatRole.USER}:
            if self.content is None:
                raise ValueError("system and user messages require content")
            if self.tool_calls or self.tool_call_id is not None:
                raise ValueError("system and user messages cannot contain tool fields")
        elif self.role is ChatRole.ASSISTANT:
            if self.content is None and not self.tool_calls:
                raise ValueError("assistant message requires content or tool calls")
            if self.tool_call_id is not None:
                raise ValueError("assistant messages cannot contain tool_call_id")
        elif self.role is ChatRole.TOOL:
            if self.content is None or self.tool_call_id is None:
                raise ValueError("tool messages require content and tool_call_id")
            if self.tool_calls:
                raise ValueError("tool messages cannot contain tool_calls")
        return self

    def to_api_dict(self) -> dict[str, Any]:
        """Return the minimal OpenAI-compatible message shape."""

        result: dict[str, Any] = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.tool_calls:
            result["tool_calls"] = [
                tool_call.model_dump(mode="json") for tool_call in self.tool_calls
            ]
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        return result


class TokenUsage(BaseModel):
    """Token counts returned by the compatible endpoint."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    def add(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class ChatResult(BaseModel):
    """Stable result returned by the NetPilot LLM layer."""

    content: str | None = Field(default=None, max_length=20_000)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str = Field(min_length=1)
    finish_reason: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    request_id: str | None = None
    duration_ms: float = Field(ge=0)

    @field_validator("content")
    @classmethod
    def strip_optional_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_content_or_tool_calls(self) -> "ChatResult":
        if self.content is None and not self.tool_calls:
            raise ValueError("chat result requires content or tool calls")
        return self

    def to_assistant_message(self) -> ChatMessage:
        return ChatMessage(
            role=ChatRole.ASSISTANT,
            content=self.content,
            tool_calls=self.tool_calls,
        )
