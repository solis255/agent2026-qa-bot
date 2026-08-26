from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
import socket
import subprocess

from netpilot.agent import AgentOrchestrator, AgentStatus, ToolRegistry
from netpilot.config import Settings
from netpilot.llm import ChatMessage, ChatResult, FunctionCall, ToolCall
from netpilot.tools import build_network_tools


class DNSDiagnosisLLM:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    def chat(
        self,
        messages: Sequence[ChatMessage],
        **_kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if len(self.calls) == 1:
            return ChatResult(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_public_ip",
                        function=FunctionCall(
                            name="ping_host",
                            arguments='{"host":"1.1.1.1","count":1}',
                        ),
                    ),
                    ToolCall(
                        id="call_dns",
                        function=FunctionCall(
                            name="dns_lookup",
                            arguments='{"domain":"github.com"}',
                        ),
                    ),
                ],
                model="fake-tju-llm",
                duration_ms=1,
            )
        return ChatResult(
            content=(
                "问题判断：当前更可能是 DNS 故障。\n"
                "检测结果：公网 IP 可达，但 github.com 解析失败。\n"
                "建议操作：检查 DNS 配置后重试。"
            ),
            model="fake-tju-llm",
            duration_ms=1,
        )


def _fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("DNS mock Agent must not access the real network")


def test_dns_failure_mock_completes_an_automatic_diagnosis(
    monkeypatch,
) -> None:
    monkeypatch.setattr(socket, "create_connection", _fail_if_called)
    monkeypatch.setattr(subprocess, "run", _fail_if_called)
    monkeypatch.setattr(httpx, "get", _fail_if_called)
    settings = Settings(
        _env_file=None,
        tool_mode="mock",
        mock_scenario="dns_failure",
    )
    registry = ToolRegistry(build_network_tools(settings))
    llm = DNSDiagnosisLLM()

    diagnosis = AgentOrchestrator(llm, registry).run("为什么 github.com 打不开？")

    assert diagnosis.status is AgentStatus.COMPLETED
    assert diagnosis.tool_rounds == 1
    assert "DNS" in diagnosis.answer
    assert diagnosis.steps[0].result.data.reachable is True
    assert diagnosis.steps[1].result.data.resolved is False
    assert [step.tool_call_id for step in diagnosis.steps] == [
        "call_public_ip",
        "call_dns",
    ]
