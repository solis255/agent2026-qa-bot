from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from conftest import register_test_user
from fastapi.testclient import TestClient

from netpilot.agent import (
    AgentOrchestrator,
    SessionStore,
    ToolRegistry,
    canonical_tool_signature,
)
from netpilot.config import Settings
from netpilot.llm import ChatMessage, ChatResult, FunctionCall, TokenUsage, ToolCall
from netpilot.tools import build_network_tools
from netpilot.main import create_app


def _result(
    content: str | None = None,
    *,
    tool_call: ToolCall | None = None,
) -> ChatResult:
    return ChatResult(
        content=content,
        tool_calls=[tool_call] if tool_call else [],
        model="fake-tju-llm",
        finish_reason="tool_calls" if tool_call else "stop",
        usage=TokenUsage(prompt_tokens=2, completion_tokens=1, total_tokens=3),
        duration_ms=1,
    )


def _call(call_id: str, name: str, arguments: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        function=FunctionCall(name=name, arguments=arguments),
    )


class SequenceLLM:
    def __init__(self, responses: list[ChatResult]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResult:
        self.calls.append({"messages": list(messages), **kwargs})
        return self.responses.pop(0)


def _registry() -> ToolRegistry:
    settings = Settings(
        _env_file=None,
        tool_mode="mock",
        mock_scenario="dns_failure",
    )
    return ToolRegistry(build_network_tools(settings))


def test_tool_signature_materializes_defaults_and_normalizes_targets() -> None:
    registry = _registry()
    implicit = registry.normalize_arguments(
        "tcp_check", '{"port":22,"host":"GitHub.COM."}'
    )
    explicit = registry.normalize_arguments(
        "tcp_check", '{"host":"github.com","timeout":3,"port":22}'
    )

    assert implicit == explicit == {"host": "github.com", "port": 22, "timeout": 3.0}
    assert canonical_tool_signature("tcp_check", implicit) == (
        'tcp_check:{"host":"github.com","port":22,"timeout":3.0}'
    )
    assert canonical_tool_signature(
        "http_check", {"url": "https://EXAMPLE.com:443"}
    ) == canonical_tool_signature(
        "http_check", {"url": "https://example.com/"}
    )


def test_same_session_reuses_prior_structured_tool_evidence() -> None:
    llm = SequenceLLM(
        [
            _result(tool_call=_call("turn1-dns", "dns_lookup", '{"domain":"GitHub.COM."}')),
            _result("第一轮确认 DNS 解析异常。"),
            _result(tool_call=_call("turn2-dns", "dns_lookup", '{ "domain": "github.com" }')),
            _result("第二轮基于上一轮证据继续分析，没有重新执行 DNS。"),
        ]
    )
    registry = _registry()
    execute_count = 0
    execute = registry.execute

    def counted_execute(tool_name: str, raw_arguments: str):
        nonlocal execute_count
        execute_count += 1
        return execute(tool_name, raw_arguments)

    registry.execute = counted_execute  # type: ignore[method-assign]
    agent = AgentOrchestrator(llm, registry)
    owner = uuid4()
    sessions = SessionStore()
    session = sessions.create(owner)

    first_history = sessions.begin_turn(session.session_id, owner)
    first = agent.run(
        "检查 github.com 的 DNS",
        history=first_history,
        task_state=sessions.task_state(session.session_id, owner),
    )
    sessions.finish_turn(
        session.session_id,
        "检查 github.com 的 DNS",
        first.answer,
        result=first,
    )
    stored = sessions.task_state(session.session_id, owner)
    evidence_id = stored.evidence[0].evidence_id

    second_history = sessions.begin_turn(session.session_id, owner)
    second = agent.run(
        "继续检查 github.com 的 DNS。",
        history=second_history,
        task_state=sessions.task_state(session.session_id, owner),
    )
    sessions.finish_turn(
        session.session_id,
        "继续检查 github.com 的 DNS。",
        second.answer,
        result=second,
    )

    assert execute_count == 1
    assert second.steps == []
    assert second.reused_evidence_ids == [evidence_id]
    assert sessions.get(session.session_id, owner).evidence_count == 1
    finalization_messages = llm.calls[3]["messages"]
    reused_message = next(
        message
        for message in reversed(finalization_messages)
        if message.role.value == "tool"
    )
    reused_feedback = json.loads(reused_message.content)
    assert reused_feedback["reused"] is True
    assert reused_feedback["evidence_id"] == evidence_id
    assert reused_feedback["evidence"]["resolved"] == "no"
    assert llm.calls[3]["tool_choice"] == "none"


def test_task_state_is_injected_before_followup_user_message() -> None:
    llm = SequenceLLM(
        [
            _result(tool_call=_call("dns", "dns_lookup", '{"domain":"github.com"}')),
            _result("已记录。"),
            _result("直接使用已有证据回答。"),
        ]
    )
    agent = AgentOrchestrator(llm, _registry())
    owner = uuid4()
    sessions = SessionStore()
    session = sessions.create(owner)
    history = sessions.begin_turn(session.session_id, owner)
    first = agent.run("检查 DNS", history=history, task_state=sessions.task_state(session.session_id, owner))
    sessions.finish_turn(session.session_id, "检查 DNS", first.answer, result=first)

    history = sessions.begin_turn(session.session_id, owner)
    agent.run("刚才发现了什么？", history=history, task_state=sessions.task_state(session.session_id, owner))

    messages = llm.calls[2]["messages"]
    context = next(
        message
        for message in messages
        if message.role.value == "system" and "ABNORMAL EVIDENCE" in message.content
    )
    assert "dns_lookup" in context.content
    assert '"resolved":false' not in context.content
    assert messages[-1].content == "刚才发现了什么？"


def test_chat_api_reuses_evidence_from_the_same_session(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        tju_api_key="evidence-api-test-key",
        tool_mode="mock",
        mock_scenario="dns_failure",
        rag_enabled=False,
        diagnosis_history_enabled=False,
        diagnosis_db_path=tmp_path / "evidence.db",
    )
    application = create_app(settings)
    llm = SequenceLLM(
        [
            _result(tool_call=_call("api-1", "dns_lookup", '{"domain":"github.com"}')),
            _result("第一轮完成。"),
            _result(tool_call=_call("api-2", "dns_lookup", '{"domain":"github.com."}')),
            _result("第二轮复用完成。"),
        ]
    )
    application.state.agent = AgentOrchestrator(llm, application.state.tool_registry)

    with TestClient(application) as client:
        register_test_user(client)
        session_id = client.post("/api/session").json()["session_id"]
        first = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "检查 DNS"},
        )
        second = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "继续检查 github.com 的 DNS"},
        )
        owner = UUID(client.get("/api/auth/me").json()["id"])
        state = application.state.sessions.task_state(
            UUID(session_id),
            owner,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(first.json()["tool_calls"]) == 1
    assert second.json()["tool_calls"] == []
    assert len(state.evidence) == 1
    assert llm.calls[3]["tool_choice"] == "none"
