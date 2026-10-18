"""Intent-derived allowlist policy layered over the Tool Registry."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from netpilot.agent.intent import IntentClassification, TurnIntent
from netpilot.agent.target_capabilities import TargetCapability


class ToolPolicy(BaseModel):
    """Capabilities permitted for one turn; Registry validation still applies."""

    model_config = ConfigDict(extra="forbid")

    allow_network_tools: bool = False
    allow_rag: bool = False
    blocked_signatures: set[str] = Field(default_factory=set)
    max_new_calls: int | None = Field(default=None, ge=0)
    rationale: str = Field(min_length=1)
    target_capability: TargetCapability | None = None

    @property
    def allows_any_tool(self) -> bool:
        return self.allow_network_tools or self.allow_rag

    def filter_schemas(
        self,
        schemas: list[dict[str, Any]],
        *, execution_scopes: dict[str, str],
    ) -> list[dict[str, Any]]:
        allowed: list[dict[str, Any]] = []
        for schema in schemas:
            name = schema["function"]["name"]
            scope = execution_scopes.get(name)
            if self.target_capability is not None and not self.target_capability.allows_scope(scope):
                continue
            if scope == "target_neutral" and self.allow_rag:
                allowed.append(schema)
            elif scope in {"execution_host", "mock_target"} and self.allow_network_tools:
                allowed.append(schema)
        return allowed


def build_tool_policy(
    classification: IntentClassification,
    *,
    blocked_signatures: set[str] | None = None,
) -> ToolPolicy:
    intent = classification.intent
    blocked = set(blocked_signatures or ())
    if intent in {TurnIntent.DIAGNOSE, TurnIntent.STATE_CHANGED}:
        return ToolPolicy(
            allow_network_tools=True,
            blocked_signatures=blocked,
            rationale="real-time diagnosis requires allowlisted read-only evidence",
        )
    if intent is TurnIntent.KNOWLEDGE_REQUEST:
        return ToolPolicy(
            allow_rag=True,
            blocked_signatures=blocked,
            rationale="knowledge requests may use RAG but not live network tools",
        )
    if intent is TurnIntent.HISTORY_ANALYSIS:
        return ToolPolicy(
            allow_rag=classification.needs_rag,
            blocked_signatures=blocked,
            rationale="history analysis cannot run live network checks",
        )
    return ToolPolicy(
        blocked_signatures=blocked,
        max_new_calls=0,
        rationale=f"{intent.value} must use conversation and existing evidence only",
    )
