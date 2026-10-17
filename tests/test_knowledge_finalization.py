from uuid import uuid4

import pytest

from netpilot.agent import AgentOrchestrator, FallbackReason, ResponseMode, ToolRegistry, TurnIntent
from netpilot.api.presenters import present_chat
from netpilot.config import Settings
from netpilot.llm import ChatResult, FunctionCall, LLMTimeoutError, ToolCall
from netpilot.rag import KnowledgeSearchResult
from netpilot.tools import build_network_tools


class Retriever:
    def search(self, query, top_k=None):
        return [
            KnowledgeSearchResult(
                title=f"VPN 资料 {index}", source=f"https://example.test/{index}",
                source_type=source_type, file=f"vpn-{index}.md",
                chunk_id=f"vpn-chunk-{index}", score=0.9 - index / 100,
                content=f"真实片段 {index}：校外使用 VPN 访问校内资源，请先安装客户端。" + "原文" * 1000,
            )
            for index, source_type in enumerate(["official", "community", "maintainer"])
        ]


class LLM:
    def __init__(self, finalizations):
        self.finalizations = list(finalizations)
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((list(messages), kwargs))
        if len(self.calls) == 1:
            return ChatResult(
                model="test", duration_ms=1,
                tool_calls=[ToolCall(id="rag-call", function=FunctionCall(
                    name="knowledge_search", arguments='{"query":"天津大学 VPN 使用"}'
                ))],
            )
        value = self.finalizations.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def completed(text="请先安装资料中说明的客户端，再按指引访问校内资源。"):
    return ChatResult(content=text, model="test", duration_ms=1)


def run(llm):
    registry = ToolRegistry(build_network_tools(Settings(_env_file=None)), Retriever())
    return AgentOrchestrator(llm, registry).run("天津大学 VPN 怎么使用？请检索知识库并标出来源。")


def test_knowledge_finalization_answers_using_bounded_original_content():
    llm = LLM([completed()])
    result = run(llm)
    assert "安装" in result.answer
    assert "模型未能完成最终整理" not in result.answer
    assert len(result.sources) == 3
    assert {s.source_type.value for s in result.sources} == {"official", "community", "maintainer"}
    assert result.knowledge_finalization_attempts == 1
    assert result.rag_calls == 1
    assert result.fallback_reason is None
    prompt = "\n".join(m.content or "" for m in llm.calls[1][0])
    assert all(f"真实片段 {index}" in prompt for index in range(3))
    assert len(prompt) < 10000
    assert len(result.steps[0].result.data.results[0].content) > 900
    assert llm.calls[1][1]["tools"] is None
    assert llm.calls[1][1]["tool_choice"] == "none"


def test_knowledge_finalization_retries_once_with_shorter_context():
    llm = LLM([LLMTimeoutError("timeout", retryable=True), completed()])
    result = run(llm)
    assert result.knowledge_finalization_attempts == 2
    assert result.fallback_reason is None
    assert len(llm.calls) == 3
    assert len(llm.calls[2][0][2].content) < len(llm.calls[1][0][2].content)
    assert all(call[1]["tools"] is None for call in llm.calls[1:])
    assert all(call[1]["tool_choice"] == "none" for call in llm.calls[1:])


def test_final_sources_prefer_chunks_actually_cited_in_synthesis():
    result = run(LLM([completed("请先安装客户端。来源 [official] https://example.test/0")]))
    assert [source.source for source in result.sources] == ["https://example.test/0"]
    assert "https://example.test/2" not in result.answer


@pytest.mark.parametrize("question", [
    "请检索知识库，比较天津大学 VPN 在校内与校外的使用区别。",
    "天津大学 VPN 怎么使用？还是请检索知识库并标出来源。",
    "基于刚才的结果，检索知识库对比 VPN 的使用方式。",
])
def test_sourced_comparison_retrieves_and_finalizes_without_comparison_refusal(question):
    llm = LLM([completed()])
    registry = ToolRegistry(build_network_tools(Settings(_env_file=None)), Retriever())
    result = AgentOrchestrator(llm, registry).run(question)
    assert result.turn_intent is TurnIntent.KNOWLEDGE_REQUEST
    assert result.response_mode is ResponseMode.KNOWLEDGE
    assert result.rag_calls == 1
    assert result.knowledge_finalization_attempts == 1
    assert [step.tool_name for step in result.steps] == ["knowledge_search"]
    assert {tool["function"]["name"] for tool in llm.calls[0][1]["tools"]} == {"knowledge_search"}
    assert "比较模式" not in "\n".join(message.content or "" for message in llm.calls[0][0])
    assert "由于当前处于比较模式" not in result.answer
    assert result.sources


@pytest.mark.parametrize("failure,reason", [
    (LLMTimeoutError("timeout", retryable=True), FallbackReason.LLM_ERROR),
    (ChatResult(model="test", duration_ms=1, tool_calls=[
        ToolCall(id="forbidden", function=FunctionCall(name="dns_lookup", arguments='{"domain":"example.com"}'))
    ]), FallbackReason.INVALID_TOOL_LOOP),
    (completed("<tool_call>again</tool_call>"), FallbackReason.FINALIZATION_FAILED),
    (completed("来源：[official] VPN 资料 0 https://example.test/0"), FallbackReason.FINALIZATION_FAILED),
])
def test_two_finalization_failures_return_real_chunks_and_observable_reason(failure, reason):
    llm = LLM([failure, failure])
    result = run(llm)
    public = present_chat(uuid4(), result)
    assert result.knowledge_finalization_attempts == 2
    assert result.fallback_reason == reason
    assert len(llm.calls) == 3
    assert len(result.steps) == 1
    assert all(f"真实片段 {index}" in result.answer for index in range(3))
    assert "https://example.test/0" in result.answer
    assert "[community]" in result.answer
    assert "原文片段" in result.answer
    assert public.metrics.response_mode == "knowledge"
    assert public.metrics.fallback_reason == reason.value
    assert public.metrics.rag_calls == 1
    assert public.metrics.knowledge_finalization_attempts == 2
