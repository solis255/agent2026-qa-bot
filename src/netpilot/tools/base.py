"""Provider contract and failure boundary for network tools."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from netpilot.tools.schemas import (
    DNSLookupData,
    DNSLookupInput,
    GetNetworkInfoInput,
    HTTPCheckData,
    HTTPCheckInput,
    NetworkInfoData,
    PingData,
    PingHostInput,
    TCPCheckData,
    TCPCheckInput,
    ToolError,
    ToolErrorCode,
    ToolResult,
    TracerouteData,
    TracerouteInput,
)


logger = logging.getLogger(__name__)
InputT = TypeVar("InputT", bound=BaseModel)
DataT = TypeVar("DataT", bound=BaseModel)


@dataclass(frozen=True)
class ToolObservation(Generic[DataT]):
    """Successful execution containing either healthy or unhealthy evidence."""

    summary: str
    data: DataT


class ToolExecutionError(RuntimeError):
    """Expected provider failure converted to a safe ToolResult."""

    def __init__(
        self,
        code: ToolErrorCode,
        message: str,
        *,
        summary: str | None = None,
        data: BaseModel | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.summary = summary or message
        self.data = data


class NetworkProvider(ABC):
    """Common public interface implemented by Mock and Local providers."""

    provider_name = "base"

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 30.0))

    def get_network_info(self) -> ToolResult[NetworkInfoData]:
        return self._execute(
            "get_network_info",
            GetNetworkInfoInput,
            {},
            self._get_network_info,
        )

    def ping_host(self, host: str, count: int = 3) -> ToolResult[PingData]:
        return self._execute(
            "ping_host",
            PingHostInput,
            {"host": host, "count": count},
            self._ping_host,
        )

    def dns_lookup(self, domain: str) -> ToolResult[DNSLookupData]:
        return self._execute(
            "dns_lookup",
            DNSLookupInput,
            {"domain": domain},
            self._dns_lookup,
        )

    def tcp_check(
        self,
        host: str,
        port: int,
        timeout: float = 3.0,
    ) -> ToolResult[TCPCheckData]:
        return self._execute(
            "tcp_check",
            TCPCheckInput,
            {"host": host, "port": port, "timeout": timeout},
            self._tcp_check,
        )

    def http_check(self, url: str) -> ToolResult[HTTPCheckData]:
        return self._execute(
            "http_check",
            HTTPCheckInput,
            {"url": url},
            self._http_check,
        )

    def traceroute(self, host: str, max_hops: int = 15) -> ToolResult[TracerouteData]:
        return self._execute(
            "traceroute",
            TracerouteInput,
            {"host": host, "max_hops": max_hops},
            self._traceroute,
        )

    def _execute(
        self,
        tool_name: str,
        input_type: type[InputT],
        values: dict[str, Any],
        operation: Callable[[InputT], ToolObservation[DataT]],
    ) -> ToolResult[DataT]:
        started = perf_counter()
        try:
            request = input_type(**values)
        except ValidationError:
            return self._failure(
                tool_name,
                started,
                ToolErrorCode.INVALID_INPUT,
                "工具参数不合法",
            )

        try:
            observation = operation(request)
            return ToolResult[DataT](
                success=True,
                tool=tool_name,
                summary=observation.summary,
                data=observation.data,
                error=None,
                duration_ms=self._duration_ms(started),
            )
        except ToolExecutionError as exc:
            return self._failure(
                tool_name,
                started,
                exc.code,
                exc.safe_message,
                summary=exc.summary,
                data=exc.data,
            )
        except Exception:
            logger.exception("Unexpected %s provider failure in %s", tool_name, self.provider_name)
            return self._failure(
                tool_name,
                started,
                ToolErrorCode.EXECUTION_ERROR,
                "工具执行失败",
            )

    @staticmethod
    def _duration_ms(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))

    def _failure(
        self,
        tool_name: str,
        started: float,
        code: ToolErrorCode,
        message: str,
        *,
        summary: str | None = None,
        data: BaseModel | None = None,
    ) -> ToolResult[Any]:
        return ToolResult[Any](
            success=False,
            tool=tool_name,
            summary=summary or message,
            data=data,
            error=ToolError(code=code, message=message),
            duration_ms=self._duration_ms(started),
        )

    @abstractmethod
    def _get_network_info(
        self, request: GetNetworkInfoInput
    ) -> ToolObservation[NetworkInfoData]:
        raise NotImplementedError

    @abstractmethod
    def _ping_host(self, request: PingHostInput) -> ToolObservation[PingData]:
        raise NotImplementedError

    @abstractmethod
    def _dns_lookup(self, request: DNSLookupInput) -> ToolObservation[DNSLookupData]:
        raise NotImplementedError

    @abstractmethod
    def _tcp_check(self, request: TCPCheckInput) -> ToolObservation[TCPCheckData]:
        raise NotImplementedError

    @abstractmethod
    def _http_check(self, request: HTTPCheckInput) -> ToolObservation[HTTPCheckData]:
        raise NotImplementedError

    @abstractmethod
    def _traceroute(self, request: TracerouteInput) -> ToolObservation[TracerouteData]:
        raise NotImplementedError
