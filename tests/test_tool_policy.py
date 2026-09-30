from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest

from netpilot.agent import (
    AgentOrchestrator,
    AgentResult,
    AgentStatus,
    AgentToolStep,
    ResponseMode,
    SessionStore,
    ToolRegistry,
    TurnIntent,
)
from netpilot.config import Settings
from netpilot.llm import (
    ChatMessage,
    ChatResult,
    FunctionCall,
    TokenUsage,
    ToolCall,
)
from netpilot.rag import KnowledgeSearchResult
from netpilot.tools import build_network_tools
from netpilot.tools.schemas import DNSLookupData, ToolResult


class DirectLLM:
    def __init__(self, answer: str = "已按当前模式回答。") -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResult:
        self.calls.append({"messages": list(messages), **kwargs})
        return ChatResult(
            content=self.answer,
            model="fake-tju-llm",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            duration_ms=1,
        )


class EmptyRetriever:
    def search(self, query: str) -> list[KnowledgeSearchResult]:
        del query
        return []


class ForbiddenToolLLM:
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResult:
        del messages, kwargs
        return ChatResult(
            tool_calls=[
                ToolCall(
                    id="forbidden-dns",
                    function=FunctionCall(
                        name="dns_lookup",
                        arguments='{"domain":"github.com"}',
                    ),
                )
            ],
            model="fake-tju-llm",
            usage=TokenUsage(),
            duration_ms=1,
        )


def _registry(*, rag: bool = True) -> ToolRegistry:
    settings = Settings(_env_file=None, tool_mode="mock", mock_scenario="dns_failure")
    return ToolRegistry(
        build_network_tools(settings),
        EmptyRetriever() if rag else None,
    )


@pytest.mark.parametrize(
    ("message", "intent", "mode"),
    [
        ("基于刚才结果继续分析", TurnIntent.ANALYZE_EXISTING, ResponseMode.ANALYSIS),
        ("整理成报告", TurnIntent.REPORT_REQUEST, ResponseMode.REPORT),
        ("这更像 DNS 还是代理问题？", TurnIntent.COMPARE, ResponseMode.COMPARISON),
        ("下一步应该怎么做？", TurnIntent.FOLLOWUP_ACTION, ResponseMode.ANALYSIS),
        ("你刚才一直重复回答", TurnIntent.META_FEEDBACK, ResponseMode.META),
        ("DNS 是什么？", TurnIntent.GENERAL_QUESTION, ResponseMode.KNOWLEDGE),
    ],
)
def test_non_diagnostic_intents_expose_no_tools(
    message: str,
    intent: TurnIntent,
    mode: ResponseMode,
) -> None:
    llm = DirectLLM()
    result = AgentOrchestrator(llm, _registry()).run(message)

    assert result.turn_intent is intent
    assert result.response_mode is mode
    assert result.steps == []
    assert llm.calls[0]["tools"] is None
    assert llm.calls[0]["tool_choice"] == "none"
    mode_messages = [
        item.content
        for item in llm.calls[0]["messages"]
        if item.role.value == "system" and "TURN RESPONSE MODE" in item.content
    ]
    assert len(mode_messages) == 1


def test_clarify_returns_deterministic_questions_without_llm_or_tools() -> None:
    llm = DirectLLM()
    result = AgentOrchestrator(llm, _registry()).run("网络有问题")

    assert result.turn_intent is TurnIntent.CLARIFY
    assert result.response_mode is ResponseMode.CLARIFICATION
    assert result.steps == []
    assert "Wi-Fi" in result.answer
    assert "VPN" in result.answer
    assert llm.calls == []


def test_knowledge_request_exposes_only_rag() -> None:
    llm = DirectLLM()
    result = AgentOrchestrator(llm, _registry()).run(
        "天津大学 VPN 怎么使用？请检索知识库"
    )

    names = {item["function"]["name"] for item in llm.calls[0]["tools"]}
    assert result.turn_intent is TurnIntent.KNOWLEDGE_REQUEST
    assert names == {"knowledge_search"}
    assert llm.calls[0]["tool_choice"] == "auto"


def test_diagnose_exposes_only_six_network_tools() -> None:
    llm = DirectLLM()
    result = AgentOrchestrator(llm, _registry()).run(
        "请诊断 github.com 打不开"
    )

    names = {item["function"]["name"] for item in llm.calls[0]["tools"]}
    assert result.turn_intent is TurnIntent.DIAGNOSE
    assert names == {
        "get_network_info",
        "ping_host",
        "dns_lookup",
        "tcp_check",
        "http_check",
        "traceroute",
    }
    assert "knowledge_search" not in names


@pytest.mark.parametrize(
    "message",
    [
        "把这次排障整理成报告",
        "你刚才一直重复回答",
    ],
)
def test_report_and_meta_cannot_execute_model_requested_network_tool(
    message: str,
) -> None:
    registry = _registry()
    executions = 0
    execute = registry.execute

    def counted_execute(tool_name: str, raw_arguments: str):
        nonlocal executions
        executions += 1
        return execute(tool_name, raw_arguments)

    registry.execute = counted_execute  # type: ignore[method-assign]
    result = AgentOrchestrator(ForbiddenToolLLM(), registry).run(message)

    assert executions == 0
    assert result.steps == []


def _existing_result() -> AgentResult:
    return AgentResult(
        answer="DNS 异常。",
        status=AgentStatus.COMPLETED,
        tool_rounds=1,
        steps=[
            AgentToolStep(
                round=1,
                tool_call_id="old-dns",
                tool_name="dns_lookup",
                arguments={"domain": "github.com"},
                tool_signature='dns_lookup:{"domain":"github.com"}',
                result=ToolResult[DNSLookupData](
                    success=True,
                    tool="dns_lookup",
                    summary="域名解析失败",
                    data=DNSLookupData(resolved=False, addresses=[]),
                    duration_ms=1,
                ),
            )
        ],
    )


def test_state_change_advances_task_version_and_hides_old_evidence() -> None:
    owner = uuid4()
    sessions = SessionStore()
    session = sessions.create(owner)
    sessions.begin_turn(session.session_id, owner)
    sessions.finish_turn(
        session.session_id,
        "检查 DNS",
        "DNS 异常。",
        result=_existing_result(),
    )
    llm = DirectLLM("已按新网络状态处理。")
    agent = AgentOrchestrator(llm, _registry())

    history = sessions.begin_turn(session.session_id, owner)
    result = agent.run(
        "我修改 DNS 后现在情况变了，请诊断",
        history=history,
        task_state=sessions.task_state(session.session_id, owner),
    )
    sessions.finish_turn(
        session.session_id,
        "我修改 DNS 后现在情况变了，请诊断",
        result.answer,
        result=result,
    )
    state = sessions.task_state(session.session_id, owner)

    assert result.turn_intent is TurnIntent.STATE_CHANGED
    assert result.task_version_advanced is True
    assert state.task_version == 2
    assert state.evidence[0].superseded is True
    assert state.last_turn_intent == "state_changed"
    assert state.last_response_mode == "diagnostic"
    assert all(
        "EXISTING SESSION EVIDENCE" not in (message.content or "")
        for message in llm.calls[0]["messages"]
    )
