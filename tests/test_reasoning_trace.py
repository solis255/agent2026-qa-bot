import json
from uuid import uuid4

import pytest

from netpilot.agent import AgentOrchestrator, ReasoningTraceBuilder, SessionStore, ToolRegistry, TurnIntent
from netpilot.agent.hypotheses import Hypothesis
from netpilot.agent.reasoning_trace import merge_reasoning_trace
from netpilot.config import Settings
from netpilot.llm import ChatResult, TokenUsage
from netpilot.rag import KnowledgeSearchResult
from netpilot.tools import build_network_tools
from reasoning_helpers import CASE_A, CASE_B, CASE_C, CASE_D, DiagnosticLLM, make_agent, run_session


def test_rt01_intent_and_rt02_complete_diagnostic_planning():
    result = make_agent().run(CASE_A)
    assert result.reasoning_trace[0].phase == "intent"
    assert result.turn_intent is TurnIntent.DIAGNOSE
    plan = next(step for step in result.reasoning_trace if step.phase == "planning")
    assert all(word in plan.summary for word in ("网络配置", "DNS", "IP", "HTTP/TCP"))


def test_rt03_dns_evidence_is_grouped_and_matches_durable_evidence_ids():
    sessions = SessionStore()
    owner = uuid4()
    sid = sessions.create(owner).session_id
    result = run_session(make_agent(), sessions, sid, owner, CASE_A)
    records = sessions.task_state(sid, owner).evidence
    dns_ids = {record.evidence_id for record in records if record.tool_name == "dns_lookup"}
    trace = [step for step in result.reasoning_trace if step.phase == "evidence" and step.title == "DNS 解析异常"]
    assert len(trace) == 1 and set(trace[0].evidence_ids) == dns_ids
    assert "2 个不同域名" in trace[0].summary
    assert all(identifier in {record.evidence_id for record in records} for step in result.reasoning_trace for identifier in step.evidence_ids)


def test_rt04_hypothesis_transitions_are_structured_not_free_text():
    builder = ReasoningTraceBuilder()
    possible = Hypothesis(name="dns_resolution_path_failure", status="possible")
    builder.observe(steps=[], evidence=[], hypotheses=[possible])
    builder.observe(steps=[], evidence=[], hypotheses=[possible.model_copy(update={"status":"supported", "supporting_evidence_ids":["E1"]})])
    step = next(step for step in builder.steps if step.phase == "hypothesis")
    assert "possible → supported" in step.summary
    assert step.hypothesis_names == [possible.name]
    assert step.evidence_ids == ["E1"]


def test_rt05_continue_and_rt06_stop_follow_actual_coverage():
    result = make_agent().run(CASE_A)
    decisions = [step for step in result.reasoning_trace if step.phase == "decision"]
    assert any(step.decision == "continue" and "HTTP/TCP" in step.summary for step in decisions)
    assert any(step.decision == "continue" and "不能区分" in step.summary and len(step.evidence_ids) >= 4 for step in decisions)
    assert any(step.decision == "stop" for step in decisions)
    assert result.evidence_sufficiency.sufficient
    assert any("DNS 解析链路" in step.summary for step in result.reasoning_trace if step.phase == "finalization")


def test_rt07_dedup_is_turn_scoped_and_bounded():
    builder = ReasoningTraceBuilder(max_steps=7)
    for _ in range(3):
        builder.append("decision", "继续检测", "仍缺证据", evidence_ids=["E2", "E1"], decision="continue")
    assert len(builder.steps) == 1
    for index in range(15):
        builder.append("evidence", f"证据 {index}", "结构化观察", evidence_ids=[f"E{index}"])
    assert len(builder.steps) <= 7
    assert any(step.phase == "decision" for step in builder.steps)
    assert merge_reasoning_trace(builder.steps, builder.steps, 7) == builder.steps


def test_rt08_state_change_keeps_old_trace_and_advances_version():
    sessions = SessionStore()
    owner = uuid4()
    sid = sessions.create(owner).session_id
    agent = make_agent()
    first = run_session(agent, sessions, sid, owner, CASE_A)
    second = run_session(agent, sessions, sid, owner, "我重新连接网络后，网页仍打不开，请完整排查。")
    state = sessions.task_state(sid, owner)
    assert state.task_version == 2
    assert any(step.phase == "state_change" and step.task_version == 2 for step in second.reasoning_trace)
    assert all(step in state.reasoning_trace for step in first.reasoning_trace)
    assert {step.turn_index for step in state.reasoning_trace} == {1, 2}


def test_rt09_fallback_is_safe_and_explains_limited_conclusion():
    result = make_agent(DiagnosticLLM(finalization_error=True)).run(CASE_A)
    assert result.fallback_reason is not None
    assert any(step.phase == "fallback" for step in result.reasoning_trace)
    serialized = json.dumps([step.model_dump(mode="json") for step in result.reasoning_trace])
    assert "private-stack-payload" not in serialized
    assert "Traceback" not in serialized
    assert CASE_A not in serialized


@pytest.mark.parametrize("message,intent,decision", [(CASE_B, TurnIntent.ANALYZE_EXISTING, "reuse"), (CASE_C, TurnIntent.REPORT_REQUEST, "report"), (CASE_D, TurnIntent.META_FEEDBACK, "meta_feedback")])
def test_evidence_reuse_report_and_meta_have_distinct_no_network_traces(message, intent, decision):
    sessions = SessionStore()
    owner = uuid4()
    sid = sessions.create(owner).session_id
    agent = make_agent()
    run_session(agent, sessions, sid, owner, CASE_A)
    result = run_session(agent, sessions, sid, owner, message)
    assert result.turn_intent is intent
    assert result.steps == []
    assert any(step.decision == decision for step in result.reasoning_trace)
    assert not any(step.title == "DNS 解析异常" for step in result.reasoning_trace)


def test_default_adds_no_llm_or_tools_and_disable_is_effective():
    enabled_llm, disabled_llm = DiagnosticLLM(), DiagnosticLLM()
    enabled = make_agent(enabled_llm).run(CASE_A)
    disabled = make_agent(disabled_llm, reasoning_trace_enabled=False).run(CASE_A)
    assert len(enabled_llm.calls) == len(disabled_llm.calls) == 3
    assert len(enabled.steps) == len(disabled.steps) == 5
    assert disabled.reasoning_trace == []
    assert enabled.reasoning_summary_llm_used is False
    assert enabled.reasoning_summary_prompt_tokens == enabled.reasoning_summary_completion_tokens == 0


@pytest.mark.parametrize("bad", [False, True])
def test_optional_summary_makes_at_most_one_safe_selection_call(bad):
    class SummaryLLM(DiagnosticLLM):
        def chat(self, messages, **options):
            if "step_index" in (messages[0].content or ""):
                self.calls.append((list(messages), options))
                if bad:
                    raise RuntimeError("never disclose optional failure stack or password")
                payload = json.loads(messages[-1].content)
                return ChatResult(content=json.dumps([item["step_index"] for item in payload[-2:]]), model="test", duration_ms=1,
                                  usage=TokenUsage(prompt_tokens=10, completion_tokens=3, total_tokens=13))
            return super().chat(messages, **options)
    llm = SummaryLLM()
    result = make_agent(llm, reasoning_summary_llm_enabled=True).run(CASE_A)
    assert len(llm.calls) == 4
    assert result.reasoning_summary_llm_used
    assert result.answer == "依据已有结构化观察整理本轮回答，未验证的原因仍需核验。"
    assert "password" not in json.dumps([step.model_dump(mode="json") for step in result.reasoning_trace])
    assert all(CASE_A not in message.content for message in llm.calls[-1][0])
    if not bad:
        assert result.reasoning_trace[-1].decision == "summary"
        assert result.reasoning_trace[-1].summary.count("- ") == 2
        assert result.reasoning_summary_prompt_tokens == 10


def test_knowledge_trace_records_source_types_not_chunk_body():
    import re
    from netpilot.llm import FunctionCall, ToolCall
    class Retriever:
        def search(self, query, top_k=None):
            return [KnowledgeSearchResult(title="VPN", source="https://example.test/vpn", source_type="community",
                                          file="vpn.md", chunk_id="vpn-chunk-001", content="RAW_CHUNK_SECRET_SENTINEL", score=.9)]
    class LLM:
        def chat(self, messages, **options):
            if options.get("tools"):
                return ChatResult(model="test", duration_ms=1, tool_calls=[ToolCall(id="rag", function=FunctionCall(name="knowledge_search", arguments='{"query":"VPN 使用"}'))])
            ref = re.search(r"source_ref=([a-f0-9]{12})", "\n".join(message.content or "" for message in messages))[1]
            return ChatResult(content=f"资料仅作参考，需核验官方说明。[[cite:{ref}]]", model="test", duration_ms=1)
    agent = AgentOrchestrator(LLM(), ToolRegistry(build_network_tools(Settings(_env_file=None)), Retriever()))
    result = agent.run("根据天津大学知识库解释 VPN。")
    serialized = json.dumps([step.model_dump(mode="json") for step in result.reasoning_trace], ensure_ascii=False)
    assert "community" in serialized and "RAW_CHUNK_SECRET_SENTINEL" not in serialized
    assert any(step.decision == "knowledge_finalization" for step in result.reasoning_trace)
