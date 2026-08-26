"""Allowlisted function schemas and dispatch for NetPilot network tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from netpilot.agent.schemas import RegistryExecution
from netpilot.rag import KnowledgeSearchData, KnowledgeSearchInput, Retriever
from netpilot.tools.schemas import (
    DNSLookupInput,
    GetNetworkInfoInput,
    HTTPCheckInput,
    PingHostInput,
    TCPCheckInput,
    ToolError,
    ToolErrorCode,
    ToolResult,
    TracerouteInput,
)
from netpilot.tools.service import NetworkToolService


logger = logging.getLogger(__name__)
ToolHandler = Callable[..., ToolResult[Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler


class ToolRegistry:
    """Expose validated read-only network and optional knowledge tools."""

    def __init__(
        self,
        service: NetworkToolService,
        retriever: Retriever | None = None,
        *,
        strict: bool = True,
    ) -> None:
        self._strict = strict
        specs = [
            ToolSpec(
                "get_network_info",
                "获取本机网卡、IP、默认网关和 DNS 配置，用于判断本地接入状态。",
                GetNetworkInfoInput,
                service.get_network_info,
            ),
            ToolSpec(
                "ping_host",
                "检测目标主机或 IP 的 ICMP 可达性、丢包率和平均时延。",
                PingHostInput,
                service.ping_host,
            ),
            ToolSpec(
                "dns_lookup",
                "解析域名并返回地址，用于确认 DNS 是否正常。",
                DNSLookupInput,
                service.dns_lookup,
            ),
            ToolSpec(
                "tcp_check",
                "检测目标主机指定 TCP 端口是否可连接。",
                TCPCheckInput,
                service.tcp_check,
            ),
            ToolSpec(
                "http_check",
                "以只读方式检测公开 HTTP/HTTPS URL 的访问结果。",
                HTTPCheckInput,
                service.http_check,
            ),
            ToolSpec(
                "traceroute",
                "以受限最大跳数追踪到目标主机的网络路径。",
                TracerouteInput,
                service.traceroute,
            ),
        ]
        if retriever is not None:
            specs.append(
                ToolSpec(
                    "knowledge_search",
                    "检索带来源的校园网络、VPN、无线网络和 eduroam 参考资料。",
                    KnowledgeSearchInput,
                    lambda query: _search_knowledge(retriever, query),
                )
            )
        self._specs = {spec.name: spec for spec in specs}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible native function definitions."""

        definitions: list[dict[str, Any]] = []
        for spec in self._specs.values():
            function: dict[str, Any] = {
                "name": spec.name,
                "description": spec.description,
                "parameters": _function_parameters(spec.input_model),
            }
            if self._strict:
                function["strict"] = True
            definitions.append({"type": "function", "function": function})
        return definitions

    def execute(self, tool_name: str, raw_arguments: str) -> RegistryExecution:
        """Validate and execute one allowlisted function call without raising."""

        started = perf_counter()
        spec = self._specs.get(tool_name)
        if spec is None:
            return RegistryExecution(
                result=_failure(
                    tool_name or "unknown",
                    ToolErrorCode.UNSUPPORTED,
                    "模型请求了未注册的工具",
                    started,
                )
            )

        try:
            payload = json.loads(raw_arguments)
        except (json.JSONDecodeError, TypeError):
            return RegistryExecution(
                result=_failure(
                    tool_name,
                    ToolErrorCode.INVALID_INPUT,
                    "工具参数不是合法 JSON",
                    started,
                )
            )
        if not isinstance(payload, dict):
            return RegistryExecution(
                result=_failure(
                    tool_name,
                    ToolErrorCode.INVALID_INPUT,
                    "工具参数必须是 JSON 对象",
                    started,
                )
            )

        try:
            request = spec.input_model.model_validate(payload)
        except ValidationError:
            return RegistryExecution(
                result=_failure(
                    tool_name,
                    ToolErrorCode.INVALID_INPUT,
                    "工具参数不合法",
                    started,
                )
            )

        arguments = request.model_dump(mode="json")
        try:
            result = spec.handler(**arguments)
        except Exception:
            logger.warning("ToolRegistry handler failed safely: %s", tool_name)
            return RegistryExecution(
                arguments=arguments,
                result=_failure(
                    tool_name,
                    ToolErrorCode.EXECUTION_ERROR,
                    "工具执行失败",
                    started,
                ),
            )
        return RegistryExecution(arguments=arguments, result=result)


def _function_parameters(input_model: type[BaseModel]) -> dict[str, Any]:
    schema = input_model.model_json_schema()
    _remove_schema_annotations(schema)
    properties = schema.get("properties", {})
    schema["type"] = "object"
    schema["properties"] = properties
    schema["required"] = list(properties)
    schema["additionalProperties"] = False
    return schema


def _remove_schema_annotations(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("title", None)
        value.pop("default", None)
        for nested in value.values():
            _remove_schema_annotations(nested)
    elif isinstance(value, list):
        for nested in value:
            _remove_schema_annotations(nested)


def _failure(
    tool_name: str,
    code: ToolErrorCode,
    message: str,
    started: float,
) -> ToolResult[Any]:
    return ToolResult[Any](
        success=False,
        tool=tool_name,
        summary=message,
        data=None,
        error=ToolError(code=code, message=message),
        duration_ms=max(0, round((perf_counter() - started) * 1000)),
    )


def _search_knowledge(retriever: Retriever, query: str) -> ToolResult[Any]:
    started = perf_counter()
    results = retriever.search(query)
    if results:
        summary = f"知识库找到 {len(results)} 条带来源的参考内容"
    else:
        summary = "知识库没有找到足够依据。"
    return ToolResult[Any](
        success=True,
        tool="knowledge_search",
        summary=summary,
        data=KnowledgeSearchData(results=results),
        error=None,
        duration_ms=max(0, round((perf_counter() - started) * 1000)),
    )
