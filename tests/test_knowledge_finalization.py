from uuid import uuid4

import pytest

from netpilot.agent import AgentOrchestrator, AgentStatus, FallbackReason, ResponseMode, SessionStore, ToolRegistry, TurnIntent
from netpilot.agent.knowledge import source_only_answer
from netpilot.agent.prompts import KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT, NETPILOT_SYSTEM_PROMPT
from netpilot.api.presenters import present_chat
from netpilot.config import Settings
from netpilot.llm import ChatResult, FunctionCall, LLMAuthenticationError, LLMRateLimitError, LLMRequestError, LLMTimeoutError, ToolCall
from netpilot.rag import KnowledgeSearchResult
from netpilot.rag.schemas import source_ref_for
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
        value = self.finalizations.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def citation(*indexes):
    return "[[cite:" + ",".join(source_ref_for(f"https://example.test/{index}", f"vpn-chunk-{index}") for index in indexes) + "]]"


def completed(text="请先安装资料中说明的客户端，再按指引访问校内资源。" + citation(0, 1, 2)):
    return ChatResult(content=text, model="test", duration_ms=1, finish_reason="stop")


def run(llm):
    registry = ToolRegistry(build_network_tools(Settings(_env_file=None)), Retriever())
    return AgentOrchestrator(llm, registry).run("天津大学 VPN 怎么使用？请检索知识库并标出来源。")


def test_knowledge_finalization_answers_using_bounded_original_content():
    llm = LLM([completed()])
    result = run(llm)
    assert "安装" in result.answer
    assert "模型未能完成最终整理" not in result.answer
    assert len(result.sources) == 3
    assert result.answer == completed().content
    assert "检索来源（参考资料）" not in result.answer
    assert not any(source.source in result.answer for source in result.sources)
    assert {s.source_type.value for s in result.sources} == {"official", "community", "maintainer"}
    assert result.knowledge_finalization_attempts == 1
    assert result.rag_calls == 1
    assert result.fallback_reason is None
    prompt = "\n".join(m.content or "" for m in llm.calls[0][0])
    assert all(f"真实片段 {index}" in prompt for index in range(3))
    assert len(prompt) < 10000
    assert len(result.steps[0].result.data.results[0].content) > 900
    assert llm.calls[0][1]["tools"] is None
    assert llm.calls[0][1]["tool_choice"] == "none"


def test_synthesis_prompts_separate_answer_from_bibliography():
    llm = LLM([completed()])
    run(llm)
    prompt = "\n".join(message.content or "" for message in llm.calls[0][0])
    assert "不要在答案末尾输出" in KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT
    assert "[S1]" in KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT
    assert "source_type" in KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT
    assert "再列来源" not in prompt
    assert "最后列出使用的来源" not in prompt
    assert "列出真实来源" not in prompt
    assert "不要生成链接或来源列表" in prompt


def test_source_type_question_keeps_substantive_type_comparison_and_metadata():
    body = (
        "| 资料 | source_type | 核验建议 |\n|---|---|---|\n"
        f"| VPN 资料 0 | official | 核验更新日期{citation(0)} |\n"
        f"| VPN 资料 1 | community | 需要官方再次核验{citation(1)} |\n"
        f"| VPN 资料 2 | maintainer | 留意维护时间{citation(2)} |"
    )
    llm = LLM([completed(body)])
    registry = ToolRegistry(build_network_tools(Settings(_env_file=None)), Retriever())
    result = AgentOrchestrator(llm, registry).run(
        "请检索 VPN 资料，并告诉我每条资料是 official、community 还是 maintainer。"
    )
    assert result.answer == body
    assert len(result.sources) == 3
    assert "http" not in result.answer
    assert {source.source_type.value for source in result.sources} == {"official", "community", "maintainer"}
    assert all(source.file and source.chunk_id and source.score for source in result.sources)


def test_knowledge_finalization_retries_once_with_shorter_context():
    llm = LLM([LLMTimeoutError("timeout", retryable=True), completed()])
    result = run(llm)
    assert result.knowledge_finalization_attempts == 2
    assert result.fallback_reason is None
    assert len(llm.calls) == 2
    assert len(llm.calls[1][0][2].content) < len(llm.calls[0][0][2].content)
    assert all(call[1]["tools"] is None for call in llm.calls)
    assert all(call[1]["tool_choice"] == "none" for call in llm.calls)


def test_vpn_retrieves_before_the_rate_limited_synthesis():
    class RateLimitedLLM:
        calls = 0

        def chat(self, messages, **kwargs):
            self.calls += 1
            raise LLMRateLimitError("rate limited", status_code=429)

    llm = RateLimitedLLM()
    registry = ToolRegistry(build_network_tools(Settings(_env_file=None)), Retriever())
    result = AgentOrchestrator(llm, registry, reasoning_summary_llm_enabled=True).run("天津大学 VPN 怎么使用？")

    assert llm.calls == 1
    assert result.status is AgentStatus.COMPLETED
    assert result.fallback_reason is FallbackReason.LLM_RATE_LIMITED
    assert result.rag_calls == 1
    assert result.knowledge_finalization_attempts == 1
    assert [step.tool_name for step in result.steps] == ["knowledge_search"]
    assert result.steps[0].arguments == {"query": "天津大学 VPN 怎么使用？"}
    assert all(citation(index) in result.answer for index in range(3))
    assert len(result.sources) == 3


def test_rate_limited_finalization_does_not_start_a_second_retry_budget():
    llm = LLM([LLMRateLimitError("rate limited", status_code=429, attempts_made=3)])
    result = run(llm)

    assert len(llm.calls) == 1
    assert "有限次数的重试" in result.answer
    assert result.status is AgentStatus.COMPLETED
    assert result.fallback_reason is FallbackReason.LLM_RATE_LIMITED
    assert result.knowledge_finalization_attempts == 1
    assert result.knowledge_finalization_failure_kind == "llm_rate_limited"
    assert all(citation(index) in result.answer for index in range(3))


@pytest.mark.parametrize("error", [
    LLMRequestError("bad request", status_code=400),
    LLMAuthenticationError("auth", status_code=401),
    LLMAuthenticationError("permissions", status_code=403),
])
def test_rejected_synthesis_request_does_not_restart_the_http_call(error):
    llm = LLM([error])
    result = run(llm)
    assert len(llm.calls) == result.knowledge_finalization_attempts == 1
    assert result.fallback_reason is FallbackReason.LLM_ERROR
    assert "429" not in result.answer and len(result.sources) == 3


@pytest.mark.parametrize("vpn_sources_available", [True, False])
def test_retrieval_searches_current_question_after_an_unrelated_fallback(vpn_sources_available):
    previous_question = "天津大学 eduroam 怎么连接？"
    vpn_question = "天津大学 VPN 怎么使用？"
    previous_source = KnowledgeSearchResult(
        title="eduroam 连接说明", source="https://example.test/eduroam", source_type="official",
        file="eduroam.md", chunk_id="eduroam-chunk-1", score=0.9, content="连接 eduroam 需要完成认证。",
    )

    class CampusRetriever(Retriever):
        def search(self, query, top_k=None):
            if query == previous_question:
                return [previous_source]
            assert query == vpn_question
            return super().search(query, top_k) if vpn_sources_available else []

    class Model:
        def __init__(self):
            self.calls = []

        def chat(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            if len(self.calls) == 1:
                raise LLMRateLimitError("rate limited", status_code=429)
            return completed()

    llm = Model()
    agent = AgentOrchestrator(llm, ToolRegistry(build_network_tools(Settings(_env_file=None)), CampusRetriever()))
    sessions = SessionStore()
    owner = uuid4()
    session = sessions.create(owner).session_id
    first = agent.run(previous_question, history=sessions.begin_turn(session, owner),
                      task_state=sessions.task_state(session, owner))
    assert first.fallback_reason is FallbackReason.LLM_RATE_LIMITED
    assert first.sources[0].source == previous_source.source
    sessions.finish_turn(session, previous_question, first.answer, result=first)

    result = agent.run(vpn_question, history=sessions.begin_turn(session, owner),
                       task_state=sessions.task_state(session, owner))

    assert result.rag_calls == 1
    assert [step.arguments for step in result.steps] == [{"query": vpn_question}]
    assert previous_source.source not in {source.source for source in result.sources}
    assert not result.reused_evidence_ids
    if vpn_sources_available:
        assert len(llm.calls) == 2
        assert llm.calls[-1][1]["tools"] is None
        assert result.knowledge_finalization_attempts == 1
        assert result.fallback_reason is None
        assert citation(0, 1, 2) in result.answer
    else:
        assert len(llm.calls) == 1
        assert result.status is AgentStatus.INSUFFICIENT_SOURCES
        assert result.knowledge_finalization_attempts == 0
        assert result.fallback_reason is FallbackReason.KNOWLEDGE_NO_SOURCES
        assert not result.sources
        assert "没有提供足够来源" in result.answer


def test_final_sources_prefer_chunks_actually_cited_in_synthesis():
    result = run(LLM([completed("根据 VPN 资料 0，请先安装客户端，并核验后续使用步骤。" + citation(0))]))
    assert [source.source for source in result.sources] == ["https://example.test/0"]
    assert "https://example.test/2" not in result.answer


def test_citation_mapping_uses_refs_not_mentioned_titles_or_urls():
    answer = "VPN 资料 0 的事项仍待核验，本句实际依据另一份社区片段。" + citation(1)
    result = run(LLM([completed(answer)]))
    assert result.answer == answer
    assert [source.source_ref for source in result.sources] == [source_ref_for("https://example.test/1", "vpn-chunk-1")]


@pytest.mark.parametrize("answer,kind", [
    ("VPN 使用说明。[[cite:does-not-exist]]", "citation_invalid"),
    ("VPN 使用说明。[[cite:0]]", "citation_invalid"),
    ("VPN 使用说明。[[cite:]]", "citation_invalid"),
    ("VPN 使用说明。[[cite:unclosed", "citation_invalid"),
])
def test_bad_citations_retry_then_fallback_preserves_provenance(answer, kind):
    result_llm = LLM([completed(answer), completed(answer)])
    result = run(result_llm)
    assert result.knowledge_finalization_attempts == 2
    assert result.knowledge_finalization_failure_kind == kind
    assert result.fallback_reason == FallbackReason.FINALIZATION_FAILED
    assert all(citation(index) in result.answer for index in range(3))
    assert "http" not in result.answer
    assert "请使用当前片段旁的 [S1] / [S2]" in result_llm.calls[1][0][2].content


def test_missing_citations_keep_body_and_selected_sources_without_retry():
    result = run(LLM([completed("请先安装客户端。")]))
    assert result.fallback_reason is None
    assert result.knowledge_finalization_attempts == 1
    assert len(result.steps) == 1
    assert result.knowledge_finalization_failure_kind == "citation_missing"
    assert present_chat(uuid4(), result).metrics.citation_mode == "source_panel_only"
    assert result.answer == "请先安装客户端。"
    assert len(result.sources) == 3


def test_marker_only_is_not_a_substantive_answer():
    assert source_only_answer(citation(0, 1), Retriever().search("VPN")) is True


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
    assert len(llm.calls) == 1
    assert llm.calls[0][1]["tools"] is None
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
    assert len(llm.calls) == 2
    assert len(result.steps) == 1
    assert all(f"真实片段 {index}" in result.answer for index in range(3))
    assert "https://example.test/0" not in result.answer
    assert all(citation(index) in result.answer for index in range(3))
    assert public.sources[0].source == "https://example.test/0"
    assert "[community]" in result.answer
    assert "原文片段" in result.answer
    assert "429" not in result.answer
    assert public.metrics.response_mode == "knowledge"
    assert public.metrics.fallback_reason == reason.value
    assert public.metrics.rag_calls == 1
    assert public.metrics.knowledge_finalization_attempts == 2


def test_synthesis_uses_knowledge_only_prompt_and_dedicated_token_budget():
    llm = LLM([completed()])
    agent = AgentOrchestrator(llm, ToolRegistry(
        build_network_tools(Settings(_env_file=None)), Retriever()
    ), max_output_tokens=800, knowledge_max_output_tokens=2300)
    agent.run("请检索天津大学 VPN 知识库资料。")
    assert len(llm.calls) == 1
    assert llm.calls[0][1]["max_tokens"] == 2300
    assert llm.calls[0][0][0].content == KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT.strip()
    assert all(message.content != NETPILOT_SYSTEM_PROMPT for message in llm.calls[0][0])


def test_knowledge_followup_reuses_evidence_and_retains_short_text_history():
    class CampusRetriever:
        def __init__(self):
            self.calls = 0

        def search(self, query, top_k=None):
            self.calls += 1
            return [KnowledgeSearchResult(
                title=topic, source=f"https://example.test/{index}",
                source_type=source_type, file=f"topic-{index}.md",
                chunk_id=f"campus-chunk-{index}", score=0.9,
                content=f"{topic}：配置可能更新，需要按官方资料再次核验。",
            ) for index, (topic, source_type) in enumerate([
                ("VPN", "official"), ("校园网", "community"), ("eduroam", "official"),
            ])]

    retriever = CampusRetriever()
    refs = [source_ref_for(f"https://example.test/{index}", f"campus-chunk-{index}") for index in range(3)]
    llm = LLM([
        completed("VPN、校园网与 eduroam 的资料性质如下：校园网为 community，其余为 official。[[cite:" + ",".join(refs) + "]]"),
        completed("community 校园网资料中的配置可能更新，应以官方说明再次核验。[[cite:" + refs[1] + "]]"),
    ])
    agent = AgentOrchestrator(llm, ToolRegistry(build_network_tools(Settings(_env_file=None)), retriever))
    sessions = SessionStore()
    owner = uuid4()
    session = sessions.create(owner).session_id
    question = "请检索 VPN、校园网和 eduroam，并标明 source_type。"
    first = agent.run(question, history=sessions.begin_turn(session, owner),
                      task_state=sessions.task_state(session, owner))
    sessions.finish_turn(session, question, first.answer, result=first)
    followup = "请把 community 来源中可能需要官方再次核验的内容单独列出来。"
    second = agent.run(followup, history=sessions.begin_turn(session, owner),
                       task_state=sessions.task_state(session, owner))
    assert retriever.calls == 1
    assert second.rag_calls == 0
    assert second.steps == []
    assert second.reused_evidence_ids
    assert second.knowledge_finalization_attempts == 1
    assert second.fallback_reason is None
    assert "community 校园网" in second.answer
    messages, options = llm.calls[-1]
    assert options["tools"] is None and options["tool_choice"] == "none"
    assert question in [message.content for message in messages]
    assert first.answer[:1000] in [message.content for message in messages]
    assert messages[-1].content == followup


@pytest.mark.parametrize("answer,expected", [
    ("来源：\n- [official] VPN 资料 0 https://example.test/0\n- [community] VPN 资料 1 https://example.test/1", True),
    ("参考来源：\n- [official] VPN 资料 0 https://example.test/0", True),
    ("- [official] 另一份标题 https://example.test/new\n- [community] 社区摘要 https://example.test/community", True),
    ("先认证。", False),
    ("VPN 需核验。\n来源：[community] VPN 资料 1 https://example.test/1", False),
    ("根据资料，新生校园网接入应先完成认证。VPN 资料中 community 来源需要进一步以官方说明核验。\n来源：\n- [official] VPN 资料 0 https://example.test/0", False),
])
def test_source_only_preserves_short_substantive_chinese(answer, expected):
    assert source_only_answer(answer, Retriever().search("VPN")) is expected


def test_length_retry_shortens_context_and_asks_for_concise_body():
    truncated = completed("正文尚未完成")
    truncated.finish_reason = "length"
    llm = LLM([truncated, completed("请先安装资料中的客户端。" + citation(0, 1))])
    result = run(llm)
    assert result.fallback_reason is None
    assert result.knowledge_finalization_attempts == 2
    assert result.knowledge_finalization_failure_kind == "model_length"
    assert "缩短正文" in llm.calls[1][0][2].content
    assert len(llm.calls[1][0][2].content) < len(llm.calls[0][0][2].content)


def test_failure_log_records_each_observation_without_raw_prompt_or_error_secrets(caplog):
    import json
    import logging
    llm = LLM([completed("来源：[official] VPN 资料 0 https://example.test/0")] * 2)
    with caplog.at_level(logging.INFO, logger="netpilot.agent.orchestrator"):
        result = run(llm)
    logs = [json.loads(record.message) for record in caplog.records
            if record.name == "netpilot.agent.orchestrator"]
    assert len(logs) == 2
    assert [item["attempt"] for item in logs] == [1, 2]
    for item in logs:
        assert item["failure_kind"] == "source_only"
        assert item["finish_reason"] == "stop"
        assert item["has_content"] is True
        assert item["content_length"] > 0
        assert item["has_tool_calls"] is False
        assert item["looks_like_textual_tool_call"] is False
        assert item["source_only_detected"] is True
        assert item["selected_chunk_count"] > 0
        assert item["selected_context_chars"] > 0
        assert item["llm_error_type"] is None
    assert "实质正文" in llm.calls[1][0][2].content
    assert result.knowledge_finalization_failure_kind == "source_only"
    assert present_chat(uuid4(), result).metrics.knowledge_finalization_failure_kind == "source_only"


def test_llm_error_log_records_type_without_error_payload(caplog):
    import json
    import logging
    llm = LLM([LLMTimeoutError("private password=secret-value", retryable=True)] * 2)
    with caplog.at_level(logging.INFO, logger="netpilot.agent.orchestrator"):
        result = run(llm)
    log = json.loads(caplog.records[-1].message)
    assert log["failure_kind"] == "model_request_failed"
    assert log["llm_error_type"] == "LLMTimeoutError"
    assert "secret-value" not in caplog.text
    assert result.knowledge_finalization_failure_kind == "model_request_failed"


@pytest.mark.parametrize("bad,kind,retry_text", [
    (completed('<tool_call>knowledge_search</tool_call>'), "model_textual_tool_call", "无任何工具"),
    (completed('{"name":"knowledge_search","arguments":{"query":"VPN"}}'), "model_textual_tool_call", "无任何工具"),
    (ChatResult(model="test", duration_ms=1, tool_calls=[ToolCall(id="illegal", function=FunctionCall(
        name="knowledge_search", arguments='{"query":"VPN"}'
    ))]), "model_tool_call", "禁止函数请求"),
    (completed("知识库检索已完成，但模型最终整理失败。"), "model_repeated_fallback", "不重复失败提示"),
])
def test_retry_guidance_matches_failed_synthesis(bad, kind, retry_text):
    result_llm = LLM([bad, completed()])
    result = run(result_llm)
    assert result.knowledge_finalization_attempts == 2
    assert result.knowledge_finalization_failure_kind == kind
    assert result.fallback_reason is None
    assert retry_text in result_llm.calls[1][0][2].content
    assert len(result.steps) == 1
