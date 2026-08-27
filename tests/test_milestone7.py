from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from netpilot.agent import AgentOrchestrator, AgentStatus, AgentToolStep, ToolRegistry
from netpilot.agent.diagnosis import assess_diagnosis, build_diagnostic_answer, step_status
from netpilot.config import Settings
from netpilot.llm import ChatMessage, ChatResult, TokenUsage
from netpilot.main import create_app
from netpilot.rag import KnowledgeSearchResult
from netpilot.tools import build_network_tools
from netpilot.tools.schemas import (
    DNSLookupData,
    HTTPCheckData,
    PingData,
    ToolError,
    ToolErrorCode,
    ToolResult,
)


def _step(
    name: str,
    result: ToolResult[Any],
    arguments: dict[str, Any],
) -> AgentToolStep:
    return AgentToolStep(
        round=1,
        tool_call_id=f"call_{name}",
        tool_name=name,
        arguments=arguments,
        result=result,
    )


def test_fake_ip_is_classified_with_specific_recovery_steps() -> None:
    steps = [
        _step(
            "dns_lookup",
            ToolResult[DNSLookupData](
                success=True,
                tool="dns_lookup",
                summary="域名解析成功",
                data=DNSLookupData(resolved=True, addresses=["198.18.0.42"]),
                duration_ms=1,
            ),
            {"domain": "www.google.com"},
        ),
        _step(
            "http_check",
            ToolResult[HTTPCheckData](
                success=False,
                tool="http_check",
                summary="HTTP 目标解析到非公网地址，安全策略已在发送请求前阻止",
                data=HTTPCheckData(
                    reachable=False,
                    final_url="https://www.google.com",
                    failure_reason="non_public_resolution",
                    request_sent=False,
                    resolved_addresses=["198.18.0.42"],
                ),
                error=ToolError(
                    code=ToolErrorCode.SECURITY_BLOCKED,
                    message="目标被安全策略阻止",
                ),
                duration_ms=1,
            ),
            {"url": "https://www.google.com"},
        ),
    ]

    assessment = assess_diagnosis(steps)
    answer = build_diagnostic_answer(steps)

    assert assessment.primary_issue == "proxy_fake_ip_mapping"
    assert assessment.confidence == "high"
    assert "Fake-IP" in assessment.summary
    assert "ipconfig /flushdns" in answer
    assert "198.18.0.0/15" in answer
    assert "HTTP 请求在发送前" in answer
    assert step_status(steps[1]) == "blocked"


def test_tool_timeout_is_inconclusive_not_unreachable() -> None:
    step = _step(
        "ping_host",
        ToolResult[PingData](
            success=False,
            tool="ping_host",
            summary="系统网络工具执行超时",
            data=None,
            error=ToolError(code=ToolErrorCode.TIMEOUT, message="执行超时"),
            duration_ms=5000,
        ),
        {"host": "1.1.1.1", "count": 3},
    )

    assessment = assess_diagnosis([step])

    assert step_status(step) == "inconclusive"
    assert assessment.primary_issue == "insufficient_evidence"
    assert "不能据此判断目标可达或不可达" in assessment.limitations[0]


class RecordingLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append({"messages": list(messages), **kwargs})
        return ChatResult(
            content="请提供更具体的现象。",
            model="fake",
            usage=TokenUsage(),
            duration_ms=1,
        )


class EmptyRetriever:
    def search(self, query: str) -> list[KnowledgeSearchResult]:
        del query
        return []


def _schema_names(call: dict[str, Any]) -> set[str]:
    return {item["function"]["name"] for item in call["tools"]}


def test_knowledge_tool_is_gated_by_campus_information_intent() -> None:
    settings = Settings(_env_file=None, tool_mode="mock", rag_enabled=False)
    registry = ToolRegistry(build_network_tools(settings), EmptyRetriever())

    general_llm = RecordingLLM()
    AgentOrchestrator(general_llm, registry).run("www.google.com 打不开，请自动诊断")
    assert "knowledge_search" not in _schema_names(general_llm.calls[0])

    campus_llm = RecordingLLM()
    AgentOrchestrator(campus_llm, registry).run("天津大学 VPN 应该怎么配置？")
    assert "knowledge_search" in _schema_names(campus_llm.calls[0])


class ApiAgent:
    def run(self, message: str, *, history=()):
        del message, history
        from netpilot.agent import AgentResult

        return AgentResult(
            answer="检测完成。",
            status=AgentStatus.COMPLETED,
            tool_rounds=0,
        )


def test_request_and_agent_logs_are_structured_and_secret_free(caplog) -> None:
    secret = "m7-super-secret-api-key"
    app = create_app(
        Settings(
            _env_file=None,
            tju_api_key=secret,
            tool_mode="mock",
            rag_enabled=False,
            log_level="INFO",
        )
    )
    app.state.agent = ApiAgent()
    supplied_request_id = "m7-request-001"

    with caplog.at_level(logging.INFO, logger="netpilot"):
        with TestClient(app) as client:
            session = client.post("/api/session").json()["session_id"]
            response = client.post(
                "/api/chat",
                headers={"X-Request-ID": supplied_request_id},
                json={"session_id": session, "message": "测试"},
            )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == supplied_request_id
    messages = [record.getMessage() for record in caplog.records]
    assert secret not in "\n".join(messages)
    payloads = [json.loads(message) for message in messages if message.startswith("{")]
    agent_event = next(item for item in payloads if item["event"] == "agent_turn")
    http_event = next(
        item
        for item in payloads
        if item["event"] == "http_request" and item["path"] == "/api/chat"
    )
    assert agent_event["request_id"] == supplied_request_id
    assert agent_event["session_id"] == session
    assert "llm_duration" in agent_event
    assert http_event["http_status"] == 200


def test_invalid_request_id_is_replaced_and_env_file_is_ignored() -> None:
    app = create_app(Settings(_env_file=None, tool_mode="mock", rag_enabled=False))
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"X-Request-ID": "bad id/with spaces"})

    request_id = response.headers["X-Request-ID"]
    assert request_id != "bad id/with spaces"
    assert len(request_id) == 32
    ignore_text = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignore_text


def test_chat_rejects_oversized_message() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            tju_api_key="test-key",
            tool_mode="mock",
            rag_enabled=False,
        )
    )
    with TestClient(app) as client:
        session = client.post("/api/session").json()["session_id"]
        response = client.post(
            "/api/chat",
            json={"session_id": session, "message": "x" * 4001},
        )

    assert response.status_code == 422
    assert UUID(session)
