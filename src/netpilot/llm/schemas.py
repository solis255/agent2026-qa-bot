"""Provider-neutral schemas for ordinary chat completions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRole(str, Enum):
    """Roles supported by the Milestone 3 ordinary chat client."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """One text-only message sent to Chat Completions."""

    model_config = ConfigDict(extra="forbid")

    role: ChatRole
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def require_non_empty_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message content must not be empty")
        return normalized

    def to_api_dict(self) -> dict[str, str]:
        """Return the minimal OpenAI-compatible message shape."""

        return {"role": self.role.value, "content": self.content}


class TokenUsage(BaseModel):
    """Token counts returned by the compatible endpoint."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ChatResult(BaseModel):
    """Stable result returned by the NetPilot LLM layer."""

    content: str = Field(min_length=1)
    model: str = Field(min_length=1)
    finish_reason: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    request_id: str | None = None
    duration_ms: float = Field(ge=0)
