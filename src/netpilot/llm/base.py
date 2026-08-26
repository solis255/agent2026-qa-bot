"""Provider-neutral LLM protocol used by the Agent orchestrator."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from netpilot.llm.schemas import ChatMessage, ChatResult


class LLMClient(Protocol):
    """Small synchronous boundary implemented by TJUClient and test fakes."""

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> ChatResult: ...
