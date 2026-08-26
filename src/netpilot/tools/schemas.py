"""Validated input and output contracts for NetPilot network tools."""

from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from netpilot.tools.validation import normalize_host, validate_http_url


class ToolErrorCode(str, Enum):
    """Stable error categories consumed by later Agent and API layers."""

    INVALID_INPUT = "invalid_input"
    TIMEOUT = "timeout"
    DNS_ERROR = "dns_error"
    UNSUPPORTED = "unsupported"
    REDIRECT_LIMIT = "redirect_limit"
    EXECUTION_ERROR = "execution_error"


class ToolError(BaseModel):
    """Safe error details that never contain command output or credentials."""

    code: ToolErrorCode
    message: str


class InterfaceInfo(BaseModel):
    """Non-sensitive interface state returned by get_network_info."""

    name: str
    is_up: bool
    ipv4: list[str] = Field(default_factory=list)
    ipv6: list[str] = Field(default_factory=list)


class NetworkInfoData(BaseModel):
    interfaces: list[InterfaceInfo] = Field(default_factory=list)
    ipv4: list[str] = Field(default_factory=list)
    ipv6: list[str] = Field(default_factory=list)
    default_gateway: str | None = None
    dns_servers: list[str] = Field(default_factory=list)


class PingData(BaseModel):
    reachable: bool
    packet_loss: float = Field(ge=0, le=100)
    avg_latency_ms: float | None = Field(default=None, ge=0)
    transmitted: int = Field(default=0, ge=0)
    received: int = Field(default=0, ge=0)


class DNSLookupData(BaseModel):
    resolved: bool
    addresses: list[str] = Field(default_factory=list)


class TCPCheckData(BaseModel):
    connected: bool
    latency_ms: float | None = Field(default=None, ge=0)
    failure_reason: str | None = None


class HTTPCheckData(BaseModel):
    reachable: bool
    status_code: int | None = Field(default=None, ge=100, le=599)
    elapsed_ms: float | None = Field(default=None, ge=0)
    redirected: bool = False
    final_url: str | None = None
    failure_reason: str | None = None


class TraceHop(BaseModel):
    hop: int = Field(ge=1)
    address: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    timed_out: bool = False


class TracerouteData(BaseModel):
    supported: bool = True
    reached_destination: bool = False
    hops: list[TraceHop] = Field(default_factory=list)


DataT = TypeVar("DataT", bound=BaseModel)


class ToolResult(BaseModel, Generic[DataT]):
    """Uniform envelope for successful checks and safely handled failures.

    ``success`` describes whether the tool executed and produced diagnostic
    evidence. A negative network observation such as ``reachable=false`` is
    still a successful tool execution and belongs in ``data``.
    """

    model_config = ConfigDict(use_enum_values=True)

    success: bool
    tool: str
    summary: str
    data: DataT | None = None
    error: ToolError | None = None
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_success_error_pair(self) -> "ToolResult[DataT]":
        if self.success and self.error is not None:
            raise ValueError("successful ToolResult must not contain an error")
        if not self.success and self.error is None:
            raise ValueError("failed ToolResult must contain an error")
        return self


class ToolInput(BaseModel):
    """Strict base for every argument object exposed to the model."""

    model_config = ConfigDict(extra="forbid")


class GetNetworkInfoInput(ToolInput):
    """Marker schema for the argument-free get_network_info tool."""


class PingHostInput(ToolInput):
    host: str = Field(description="目标主机名或 IP 地址")
    count: int = Field(default=3, ge=1, le=5, description="发送探测包数量")

    _normalize_host = field_validator("host")(normalize_host)


class DNSLookupInput(ToolInput):
    domain: str = Field(description="需要解析的域名")

    _normalize_domain = field_validator("domain")(normalize_host)


class TCPCheckInput(ToolInput):
    host: str = Field(description="目标主机名或 IP 地址")
    port: int = Field(ge=1, le=65535, description="目标 TCP 端口")
    timeout: float = Field(
        default=3.0,
        ge=1.0,
        le=10.0,
        description="连接超时秒数",
    )

    _normalize_host = field_validator("host")(normalize_host)


class HTTPCheckInput(ToolInput):
    url: str = Field(description="需要检测的 HTTP 或 HTTPS URL")

    _validate_url = field_validator("url")(validate_http_url)


class TracerouteInput(ToolInput):
    host: str = Field(description="目标主机名或 IP 地址")
    max_hops: int = Field(default=15, ge=1, le=30, description="最大跳数")

    _normalize_host = field_validator("host")(normalize_host)
