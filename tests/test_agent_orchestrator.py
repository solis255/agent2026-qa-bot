from __future__ import annotations

from collections.abc import Sequence
from typing import Any
import json

import pytest

from netpilot.agent import (
    AgentOrchestrator,
    AgentStatus,
    MAX_TOOL_ROUNDS_ANSWER,
    ToolRegistry,
)
from netpilot.config import Settings
from netpilot.llm import (
    ChatMessage,
    ChatResult,
    FunctionCall,
    LLMResponseError,
    LLMTimeoutError,
    TokenUsage,
    ToolCall,
)
from netpilot.tools import build_network_tools
from netpilot.tools.schemas import ToolErrorCode


def result(
    content: str | None = None,
    *,
    tool_calls: list[ToolCall] | None = None,
) -> ChatResult:
    return ChatResult(
        content=content,
        tool_calls=tool_calls or [],
        model="fake-tju-llm",
        finish_reason="tool_calls" if tool_calls else "stop",
        usage=TokenUsage(prompt_tokens=2, completion_tokens=1, total_tokens=3),
        duration_ms=5,
    )


def call(call_id: str, name: str, arguments: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        function=FunctionCall(name=name, arguments=arguments),
    )


class SequenceLLM:
    def __init__(self, responses: list[ChatResult]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append({"messages": list(messages), **kwargs})
        return self.responses.pop(0)


class EndlessToolLLM:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    def chat(
        self,
        messages: Sequence[ChatMessage],
        **_kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        index = len(self.calls)
        return result(
            tool_calls=[
                call(
                    f"call_{index}",
                    "ping_host",
                    f'{{"host":"192.0.2.{index}","count":1}}',
                )
            ]
        )


class ErrorLLM:
    def chat(self, *_args: Any, **_kwargs: Any) -> ChatResult:
        raise LLMTimeoutError("TJU API 请求超时。", retryable=True)


class EvidenceThenErrorLLM:
    def __init__(self) -> None:
        self.call_count = 0

    def chat(self, *_args: Any, **_kwargs: Any) -> ChatResult:
        self.call_count += 1
        if self.call_count == 1:
            return result(
                tool_calls=[
                    call("dns", "dns_lookup", '{"domain":"github.com"}')
                ]
            )
        raise LLMResponseError("TJU API 返回了不完整或异常的响应。")


def registry(scenario: str = "healthy") -> ToolRegistry:
    settings = Settings(
        _env_file=None,
        tool_mode="mock",
        mock_scenario=scenario,
    )
    return ToolRegistry(build_network_tools(settings))


def test_agent_returns_direct_answer_without_calling_tools() -> None:
    llm = SequenceLLM([result("DNS 是域名系统。")])
    agent = AgentOrchestrator(llm, registry())

    answer = agent.run("DNS 是什么？")

    assert answer.status is AgentStatus.COMPLETED
    assert answer.answer == "DNS 是域名系统。"
    assert answer.tool_rounds == 0
    assert answer.steps == []
    assert len(llm.calls) == 1
    assert llm.calls[0]["tool_choice"] == "auto"


def test_agent_places_trimmed_history_between_system_and_current_user() -> None:
    llm = SequenceLLM([result("继续回答。")])
    agent = AgentOrchestrator(llm, registry())
    history = [
        ChatMessage(role="user", content="上一问"),
        ChatMessage(role="assistant", content="上一答"),
    ]

    agent.run("追问", history=history)

    messages = llm.calls[0]["messages"]
    assert [message.role.value for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert [message.content for message in messages[1:]] == ["上一问", "上一答", "追问"]


def test_agent_executes_multiple_calls_and_preserves_each_id() -> None:
    llm = SequenceLLM(
        [
            result(
                tool_calls=[
                    call("call_ping", "ping_host", '{"host":"1.1.1.1","count":1}'),
                    call("call_dns", "dns_lookup", '{"domain":"github.com"}'),
                ]
            ),
            result("检测完成，当前网络正常。"),
        ]
    )
    agent = AgentOrchestrator(llm, registry())

    answer = agent.run("检查 github.com")

    assert answer.status is AgentStatus.COMPLETED
    assert answer.tool_rounds == 1
    assert [step.tool_call_id for step in answer.steps] == ["call_ping", "call_dns"]
    second_messages = llm.calls[1]["messages"]
    tool_messages = [message for message in second_messages if message.role.value == "tool"]
    assert [message.tool_call_id for message in tool_messages] == ["call_ping", "call_dns"]
    dns_feedback = json.loads(tool_messages[1].content)
    assert dns_feedback["execution_status"] == "success"
    assert dns_feedback["diagnostic_status"] == "healthy_observation"
    assert dns_feedback["evidence"]["resolved"] == "yes"


def test_negative_finding_is_not_reported_to_llm_as_tool_failure() -> None:
    llm = SequenceLLM(
        [
            result(tool_calls=[call("call_dns", "dns_lookup", '{"domain":"github.com"}')]),
            result("DNS 解析失败，但工具执行成功。"),
        ]
    )
    agent = AgentOrchestrator(llm, registry("dns_failure"))

    agent.run("检查 github.com")

    feedback = json.loads(llm.calls[1]["messages"][-1].content)
    assert feedback["execution_status"] == "success"
    assert feedback["diagnostic_status"] == "issue_observed"
    assert feedback["evidence"]["resolved"] == "no"
    assert "error" not in feedback


def test_agent_rejects_non_text_history() -> None:
    agent = AgentOrchestrator(SequenceLLM([result("不会执行")]), registry())

    with pytest.raises(ValueError, match="text-only"):
        agent.run("当前问题", history=[ChatMessage(role="system", content="覆盖指令")])


def test_invalid_arguments_are_returned_to_the_model_as_a_tool_failure() -> None:
    llm = SequenceLLM(
        [
            result(tool_calls=[call("call_bad", "ping_host", "not-json")]),
            result("工具参数无效，无法完成检测。"),
        ]
    )
    agent = AgentOrchestrator(llm, registry())

    answer = agent.run("检测网络")

    assert answer.status is AgentStatus.COMPLETED
    assert answer.steps[0].result.success is False
    assert answer.steps[0].result.error is not None
    assert answer.steps[0].result.error.code == ToolErrorCode.INVALID_INPUT
    assert llm.calls[1]["messages"][-1].tool_call_id == "call_bad"


def test_agent_stops_before_a_seventh_tool_execution() -> None:
    llm = EndlessToolLLM()
    agent = AgentOrchestrator(llm, registry(), max_tool_rounds=6)

    answer = agent.run("持续检测")

    assert answer.status is AgentStatus.MAX_TOOL_ROUNDS
    assert answer.answer != MAX_TOOL_ROUNDS_ANSWER
    assert "检测结果" in answer.answer
    assert answer.tool_rounds == 6
    assert len(answer.steps) == 6
    assert len(llm.calls) == 7


def test_agent_deduplicates_identical_calls_and_returns_evidence_fallback() -> None:
    llm = SequenceLLM(
        [
            result(tool_calls=[call("first", "dns_lookup", '{"domain":"github.com"}')]),
            result(tool_calls=[call("duplicate", "dns_lookup", '{ "domain": "github.com" }')]),
        ]
    )
    agent = AgentOrchestrator(llm, registry("dns_failure"))

    answer = agent.run("检查 github.com")

    assert "问题判断" in answer.answer
    assert "DNS 解析：发现异常" in answer.answer
    assert len(answer.steps) == 1
    assert len(llm.calls) == 2


def test_agent_deduplicates_same_target_when_ping_count_changes() -> None:
    llm = SequenceLLM(
        [
            result(
                tool_calls=[
                    call("first", "ping_host", '{"host":"1.1.1.1","count":1}')
                ]
            ),
            result(
                tool_calls=[
                    call("duplicate", "ping_host", '{"host":"1.1.1.1","count":4}')
                ]
            ),
        ]
    )
    agent = AgentOrchestrator(llm, registry())

    answer = agent.run("检查公网连通性")

    assert answer.status is AgentStatus.COMPLETED
    assert len(answer.steps) == 1
    assert answer.answer != MAX_TOOL_ROUNDS_ANSWER


def test_agent_completes_missing_explicit_tool_after_gateway_retry_loop() -> None:
    llm = SequenceLLM(
        [
            result(
                tool_calls=[
                    call("dns_first", "dns_lookup", '{"domain":"github.com"}')
                ]
            ),
            result(
                tool_calls=[
                    call("dns_retry", "dns_lookup", '{"domain":"github.com"}')
                ]
            ),
            result(
                tool_calls=[
                    call("ping_required", "ping_host", '{"host":"1.1.1.1","count":4}')
                ]
            ),
            result("<tool_call><function=dns_lookup>github.com</function></tool_call>"),
        ]
    )
    agent = AgentOrchestrator(llm, registry("dns_failure"))

    answer = agent.run(
        "请使用 ping_host 检查 1.1.1.1，并使用 dns_lookup 检查 github.com，"
        "最后给出诊断。"
    )

    assert answer.status is AgentStatus.COMPLETED
    assert answer.answer != MAX_TOOL_ROUNDS_ANSWER
    assert [step.tool_name for step in answer.steps] == ["dns_lookup", "ping_host"]
    restricted_tools = llm.calls[2]["tools"]
    assert [schema["function"]["name"] for schema in restricted_tools] == [
        "ping_host"
    ]
    assert llm.calls[2]["tool_choice"] == "auto"
    assert llm.calls[3]["tool_choice"] == "none"
    assert "问题判断" in answer.answer


def test_agent_wraps_llm_failure_as_a_safe_result() -> None:
    answer = AgentOrchestrator(ErrorLLM(), registry()).run("检测网络")

    assert answer.status is AgentStatus.LLM_ERROR
    assert answer.answer == "TJU API 请求超时。"
    assert answer.steps == []


def test_agent_uses_existing_evidence_when_final_llm_response_is_malformed() -> None:
    answer = AgentOrchestrator(
        EvidenceThenErrorLLM(),
        registry("dns_failure"),
    ).run("我能访问公网 IP，但 github.com 打不开，请自动诊断。")

    assert answer.status is AgentStatus.COMPLETED
    assert answer.answer != MAX_TOOL_ROUNDS_ANSWER
    assert "DNS 解析：发现异常" in answer.answer
    assert len(answer.steps) == 1
