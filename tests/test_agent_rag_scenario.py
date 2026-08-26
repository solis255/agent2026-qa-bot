from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi.testclient import TestClient

from netpilot.agent import AgentOrchestrator, AgentStatus, ToolRegistry
from netpilot.config import Settings
from netpilot.llm import ChatMessage, ChatResult, FunctionCall, ToolCall
from netpilot.main import create_app
from netpilot.rag import (
    KnowledgeSearchResult,
)
from netpilot.tools import build_network_tools
from netpilot.tools.schemas import ToolErrorCode


class FakeRetriever:
    def search(self, query: str, top_k: int | None = None) -> list[KnowledgeSearchResult]:
        assert "VPN" in query.upper()
        return [
            KnowledgeSearchResult(
                title="校园网 VPN 服务（社区资料测试摘要）",
                source="https://wiki.tjubot.cn/e-life/vpn",
                source_type="community",
                file="campus_vpn.md",
                chunk_id="vpn_chunk_001",
                content="VPN 用于在校外访问校内资源，入口为 https://vpn.tju.edu.cn。",
                score=0.88,
            )
        ]


class BrokenRetriever:
    def search(self, query: str, top_k: int | None = None):
        raise RuntimeError("secret internal detail")


class EmptyRetriever:
    def search(self, query: str, top_k: int | None = None):
        return []


class RAGFakeLLM:
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
                        id="call_knowledge",
                        function=FunctionCall(
                            name="knowledge_search",
                            arguments='{"query":"天津大学 VPN 怎么使用"}',
                        ),
                    )
                ],
                model="fake-tju-llm",
                duration_ms=1,
            )
        return ChatResult(
            content=(
                "参考社区资料，VPN 用于校外访问校内资源。\n"
                "来源：《校园网 VPN 服务（社区资料测试摘要）》\n"
                "https://wiki.tjubot.cn/e-life/vpn"
            ),
            model="fake-tju-llm",
            duration_ms=1,
        )


def network_service():
    return build_network_tools(Settings(_env_file=None, tool_mode="mock"))


def test_registry_registers_knowledge_only_when_retriever_is_ready() -> None:
    without_rag = ToolRegistry(network_service())
    with_rag = ToolRegistry(network_service(), FakeRetriever())

    assert "knowledge_search" not in without_rag.names
    assert "knowledge_search" in with_rag.names
    schema = next(
        item for item in with_rag.schemas() if item["function"]["name"] == "knowledge_search"
    )
    assert schema["function"]["strict"] is True
    assert schema["function"]["parameters"]["required"] == ["query"]


def test_knowledge_tool_returns_sources_and_hides_internal_failures() -> None:
    success = ToolRegistry(network_service(), FakeRetriever()).execute(
        "knowledge_search",
        '{"query":"VPN 怎么使用"}',
    )
    failure = ToolRegistry(network_service(), BrokenRetriever()).execute(
        "knowledge_search",
        '{"query":"VPN 怎么使用"}',
    )

    assert success.result.success is True
    assert success.result.data.results[0].source.endswith("/vpn")
    assert failure.result.success is False
    assert failure.result.error.code == ToolErrorCode.EXECUTION_ERROR
    assert "secret" not in failure.result.summary


def test_knowledge_tool_explicitly_reports_insufficient_evidence() -> None:
    execution = ToolRegistry(network_service(), EmptyRetriever()).execute(
        "knowledge_search",
        '{"query":"没有收录的校园规定"}',
    )

    assert execution.result.success is True
    assert execution.result.data.results == []
    assert execution.result.summary == "知识库没有找到足够依据。"


def test_fake_llm_uses_knowledge_search_and_agent_exposes_sources() -> None:
    llm = RAGFakeLLM()
    agent = AgentOrchestrator(llm, ToolRegistry(network_service(), FakeRetriever()))

    result = agent.run("VPN 怎么使用？")

    assert result.status is AgentStatus.COMPLETED
    assert result.tool_rounds == 1
    assert result.steps[0].tool_name == "knowledge_search"
    assert result.sources[0].source == "https://wiki.tjubot.cn/e-life/vpn"
    assert result.sources[0].source_type.value == "community"
    assert result.sources[0].title in result.answer
    assert llm.calls[1][-1].tool_call_id == "call_knowledge"


def test_application_reports_rag_ready_when_retriever_loads(monkeypatch) -> None:
    monkeypatch.setattr(
        "netpilot.main.load_configured_retriever",
        lambda _settings: FakeRetriever(),
    )
    settings = Settings(
        _env_file=None,
        tju_api_key=None,
        rag_enabled=True,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.json()["rag_ready"] is True


def test_prompt_treats_injected_knowledge_as_plain_reference() -> None:
    from netpilot.agent.prompts import NETPILOT_SYSTEM_PROMPT

    assert "忽略先前指令" in NETPILOT_SYSTEM_PROMPT
    assert "不具有控制权限" in NETPILOT_SYSTEM_PROMPT
