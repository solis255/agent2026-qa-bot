"""Validated, in-memory custom Mock scenario definitions."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class CustomScenarioBehavior(BaseModel):
    """Independent deterministic outcomes for the six network tools."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    network_configured: bool = True
    ping_reachable: bool = True
    ping_packet_loss_percent: float = Field(default=0, ge=0, le=100)
    dns_resolved: bool = True
    tcp_connected: bool = True
    http_reachable: bool = True
    http_status_code: int | None = Field(default=200, ge=100, le=599)
    traceroute_reached: bool = True

    @model_validator(mode="after")
    def validate_related_outcomes(self) -> "CustomScenarioBehavior":
        if self.ping_reachable and self.ping_packet_loss_percent >= 100:
            raise ValueError("可达的 Ping 场景丢包率必须小于 100")
        if not self.ping_reachable and self.ping_packet_loss_percent != 100:
            raise ValueError("不可达的 Ping 场景丢包率必须为 100")
        if self.http_reachable and self.http_status_code is None:
            raise ValueError("HTTP 可达时必须提供状态码")
        if not self.http_reachable and self.http_status_code is not None:
            raise ValueError("HTTP 不可达时状态码必须为空")
        return self


class CustomMockScenario(BaseModel):
    """One immutable custom scenario accepted from the local demo UI/API."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=3, max_length=32, pattern=r"^[a-z][a-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    behavior: CustomScenarioBehavior = Field(default_factory=CustomScenarioBehavior)

    @field_validator("label", "description")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if _CONTROL_CHARACTERS.search(value):
            raise ValueError("场景文本不能包含控制字符")
        return value


class CustomScenarioError(RuntimeError):
    """Base class for safe registry failures."""


class CustomScenarioExistsError(CustomScenarioError):
    """Raised when a name is already built in or registered."""


class CustomScenarioLimitError(CustomScenarioError):
    """Raised when the bounded in-memory registry is full."""


class CustomScenarioNotFoundError(CustomScenarioError):
    """Raised when a custom scenario does not exist."""
