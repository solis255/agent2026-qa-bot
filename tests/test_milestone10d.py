from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest

from netpilot.agent import (
    AgentOrchestrator,
    EvidenceRecord,
    FallbackReason,
    ResponseMode,
    SessionTaskState,
    ToolRegistry,
    TurnIntent,
    build_task_context_message,
    find_duplicate_rag_query,
)
from netpilot.api.presenters import present_chat
from netpilot.config import Settings
from netpilot.llm import (
    ChatMessage,
    ChatResult,
    FunctionCall,
    LLMTimeoutError,
    ToolCall,
)
from netpilot.main import create_app
from netpilot.rag import KnowledgeSearchResult
from netpilot.tools import build_network_tools


class CountingRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[KnowledgeSearchResult]:
        del top_k
        self.queries.append(query)
        index = len(self.queries)
        return [
            KnowledgeSearchResult(
                title=f"资料 {index}",
                source=f"https://example.test/source-{index}",
                source_type="community",
                file=f"source-{index}.md",
                chunk_id=f"chunk_{index:03d}",
                content=f"与 {query} 相关的测试资料。",
                score=0.8,
            )
        ]


class BatchedRAGLLM:
    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []

    def chat(
        self,
        messages: Sequence[ChatMessage],
        **_kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        if len(self.calls) == 1:
            queries = [
                "天津大学校园 DNS",
                "天津大学校园网 DNS",
                "天津大学 VPN 使用",
                "eduroam 无线认证故障排查",
            ]
            return ChatResult(
                tool_calls=[
                    ToolCall(
                        id=f"rag-{index}",
                        function=FunctionCall(
                            name="knowledge_search",
                            arguments=json.dumps({"query": query}, ensure_ascii=False),
                        ),
                    )
                    for index, query in enumerate(queries, start=1)
                ],
                model="fake-tju-llm",
                duration_ms=1,
            )
        return ChatResult(
            content="已按去重来源回答。",
            model="fake-tju-llm",
            duration_ms=1,
        )


class ErrorLLM:
    def chat(self, *_args: Any, **_kwargs: Any) -> ChatResult:
        raise LLMTimeoutError("TJU API 请求超时。", retryable=True)


class RecordingLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append({"messages": list(messages), **kwargs})
        return ChatResult(content="完成。", model="fake-tju-llm", duration_ms=1)


def _network_service():
    return build_network_tools(Settings(_env_file=None, tool_mode="mock"))


def _task_state() -> SessionTaskState:
    return SessionTaskState(
        session_id=uuid4(),
        owner_user_id=uuid4(),
        evidence=[
            EvidenceRecord(
                evidence_id="dns-evidence",
                tool_name="dns_lookup",
                arguments={"domain": "github.com"},
                tool_signature='dns_lookup:{"domain":"github.com"}',
                status="abnormal",
                summary="github.com 域名解析失败",
                data={"resolved": False, "addresses": [], "raw_marker": "DO_NOT_INJECT"},
                turn_index=1,
            ),
            EvidenceRecord(
                evidence_id="knowledge-evidence",
                tool_name="knowledge_search",
                arguments={"query": "天津大学 VPN 使用"},
                tool_signature='knowledge_search:{"query":"天津大学 VPN 使用"}',
                status="reference",
                summary="知识库命中 1 条资料",
                data={
                    "results": [
                        {
                            "title": "VPN 社区参考",
                            "source": "https://example.test/vpn",
                            "source_type": "community",
                            "file": "vpn.md",
                            "chunk_id": "vpn_chunk_001",
                            "content": "测试内容",
                            "score": 0.8,
                        }
                    ]
                },
                turn_index=1,
            ),
        ],
        executed_tool_signatures={
            'dns_lookup:{"domain":"github.com"}',
            'knowledge_search:{"query":"天津大学 VPN 使用"}',
        },
    )


def test_rag_queries_are_semantically_deduplicated_and_capped_at_two() -> None:
    retriever = CountingRetriever()
    llm = BatchedRAGLLM()
    result = AgentOrchestrator(
        llm,
        ToolRegistry(_network_service(), retriever),
        max_rag_calls_per_turn=2,
    ).run("请检索天津大学 DNS、VPN 和 eduroam 知识库资料")

    assert find_duplicate_rag_query(
        "天津大学校园网 DNS", ["天津大学校园 DNS"]
    ) is not None
    assert retriever.queries == ["天津大学校园 DNS", "天津大学 VPN 使用"]
    assert [step.tool_name for step in result.steps] == [
        "knowledge_search",
        "knowledge_search",
    ]
    feedback = {
        message.tool_call_id: json.loads(message.content)
        for message in llm.calls[1]
        if message.role.value == "tool"
    }
    assert feedback["rag-2"]["diagnostic_status"] == "reference_reused"
    assert feedback["rag-4"]["diagnostic_status"] == "rag_turn_limit"
    public = present_chat(uuid4(), result)
    assert public.diagnosis.evidence == []
    assert len(public.sources) == 2


def test_context_builder_separates_sources_and_omits_raw_tool_json() -> None:
    state = _task_state()
    message = build_task_context_message(
        user_message="继续分析",
        intent=TurnIntent.ANALYZE_EXISTING,
        task_version=state.task_version,
        evidence=state.evidence,
    ).content

    assert message is not None
    for heading in (
        "CURRENT TASK",
        "KNOWN FACTS",
        "ABNORMAL EVIDENCE",
        "NORMAL EVIDENCE",
        "KNOWLEDGE SOURCES",
        "UNRESOLVED HYPOTHESES",
        "ALREADY EXECUTED TOOLS",
    ):
        assert heading in message
    assert "dns_lookup" in message
    assert "https://example.test/vpn" in message
    assert "VPN 社区参考" not in message.split("KNOWLEDGE SOURCES", 1)[0]
    assert "DO_NOT_INJECT" not in message
    assert '"resolved"' not in message


@pytest.mark.parametrize(
    ("prompt", "mode", "expected"),
    [
        ("整理成报告", ResponseMode.REPORT, "现象\n"),
        ("你刚才一直重复回答", ResponseMode.META, "收到你的反馈"),
        ("基于刚才结果继续分析", ResponseMode.ANALYSIS, "已有 Network Evidence 分析"),
    ],
)
def test_fallback_is_intent_aware_and_observable(
    prompt: str,
    mode: ResponseMode,
    expected: str,
) -> None:
    result = AgentOrchestrator(ErrorLLM(), ToolRegistry(_network_service())).run(
        prompt,
        task_state=_task_state(),
    )

    assert result.response_mode is mode
    assert result.fallback_reason is FallbackReason.LLM_ERROR
    assert expected in result.answer
    assert "问题判断：目标域名没有得到可用地址" not in result.answer
    public = present_chat(uuid4(), result)
    assert public.metrics.response_mode == mode.value
    assert public.metrics.fallback_reason == "llm_error"


def test_output_token_budgets_follow_response_mode() -> None:
    llm = RecordingLLM()
    agent = AgentOrchestrator(
        llm,
        ToolRegistry(_network_service()),
        max_output_tokens=1700,
        report_max_output_tokens=2900,
    )

    agent.run("DNS 是什么？")
    agent.run("整理成报告")

    assert llm.calls[0]["max_tokens"] == 1700
    assert llm.calls[1]["max_tokens"] == 2900


def test_application_wires_configured_token_and_rag_limits() -> None:
    application = create_app(
        Settings(
            _env_file=None,
            rag_enabled=False,
            diagnosis_history_enabled=False,
            llm_max_output_tokens=1750,
            llm_report_max_output_tokens=2950,
            max_rag_calls_per_turn=3,
        )
    )

    assert application.state.agent.max_output_tokens == 1750
    assert application.state.agent.report_max_output_tokens == 2950
    assert application.state.agent.max_rag_calls_per_turn == 3
