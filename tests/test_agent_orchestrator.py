from __future__ import annotations

from collections.abc import Sequence
from typing import Any

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
            tool_calls=[call(f"call_{index}", "get_network_info", "{}")]
        )


class ErrorLLM:
    def chat(self, *_args: Any, **_kwargs: Any) -> ChatResult:
        raise LLMTimeoutError("TJU API 请求超时。", retryable=True)


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
    assert answer.answer == MAX_TOOL_ROUNDS_ANSWER
    assert answer.tool_rounds == 6
    assert len(answer.steps) == 6
    assert len(llm.calls) == 7


def test_agent_wraps_llm_failure_as_a_safe_result() -> None:
    answer = AgentOrchestrator(ErrorLLM(), registry()).run("检测网络")

    assert answer.status is AgentStatus.LLM_ERROR
    assert answer.answer == "TJU API 请求超时。"
    assert answer.steps == []
