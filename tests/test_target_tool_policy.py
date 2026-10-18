from netpilot.agent.target_capabilities import evaluate_target_capabilities
from netpilot.agent.tool_policy import build_tool_policy
from netpilot.agent.intent import classify_turn_intent
from netpilot.diagnostic_target import DiagnosticTarget, derive_diagnostic_target
from netpilot.environment import EnvironmentProfile
from target_helpers import local_session, registry_and_counts, run


def test_dt02_all_six_host_handlers_blocked_in_schema_and_execution_boundary():
    _, registry, counts = registry_and_counts(rag=True)
    target = derive_diagnostic_target(EnvironmentProfile(client_mode="remote_browser"),"local")
    policy = build_tool_policy(classify_turn_intent("请检测网络"))
    policy.target_capability = evaluate_target_capabilities(target,"local")
    assert policy.filter_schemas(registry.schemas(),execution_scopes=registry.execution_scopes) == []
    for name in counts:
        denied = registry.execute(name,"{}",target=target)
        assert denied.result.error.code.value == "security_blocked"
    assert sum(counts.values()) == 0
    assert registry.execution_scopes["knowledge_search"] == "target_neutral"
    assert all(registry.execution_scopes[name] == "execution_host" for name in counts)


def test_dt03_knowledge_neutral_allowed_remote_and_actual_rag_runs():
    agent,store,sid,owner,counts,llm = local_session(rag=True)
    result = run(agent,store,sid,owner,"天津大学 VPN 怎么使用？请检索知识库并标出来源。")
    assert result.rag_calls == 1 and result.sources
    assert result.steps[0].execution_scope == "target_neutral"
    assert result.steps[0].target_subject == "unknown"
    assert result.steps[0].execution_context == "unavailable"
    assert sum(counts.values()) == 0


def test_llm_requesting_unoffered_host_tools_during_rag_never_reaches_handlers():
    from netpilot.llm import ChatResult, FunctionCall, ToolCall
    from target_helpers import TargetLLM, NETWORK_TOOLS
    class AdversarialLLM(TargetLLM):
        def chat(self,messages,**options):
            result = super().chat(messages,**options)
            if any(call.function.name == "knowledge_search" for call in result.tool_calls):
                result = result.model_copy(update={"tool_calls":[
                    *result.tool_calls,
                    *(ToolCall(id=name,function=FunctionCall(name=name,arguments="{}")) for name in NETWORK_TOOLS),
                ]})
            return result
    agent,store,sid,owner,counts,_ = local_session(rag=True)
    agent.llm = AdversarialLLM()
    result = run(agent,store,sid,owner,"天津大学 VPN 怎么使用？请检索知识库并标出来源。")
    assert sum(counts.values()) == 0 and result.rag_calls == 1
    assert [step.tool_name for step in result.steps] == ["knowledge_search"]
    assert sum(step.title == "限制不适用的检测" for step in result.reasoning_trace) == 1


def test_capability_does_not_trust_persisted_applicability_or_limitation():
    forged = DiagnosticTarget(subject="user_client",relationship_to_netpilot="remote",execution_context="netpilot_host",limitation_code="none")
    assert not evaluate_target_capabilities(forged,"local").can_use_host_network_tools
    assert not evaluate_target_capabilities(forged,"unavailable").can_use_host_network_tools
    assert not evaluate_target_capabilities(forged,"mock").can_use_mock_tools


def test_dt04_explicit_host_tools_and_wording():
    agent,store,sid,owner,counts,llm = local_session()
    result = run(agent,store,sid,owner,"检查这台 NetPilot 服务器的 DNS，调用 dns_lookup。")
    assert counts["dns_lookup"] == 1
    assert result.diagnostic_target.subject == "netpilot_host"
    assert result.diagnostic_target.source == "user"
    assert result.steps[0].target_subject == "netpilot_host"
    assert "NetPilot 服务主机" in result.answer and "你的设备 DNS 正常" not in result.answer


def test_dt06_unknown_target_asks_first_without_handlers_or_llm():
    agent,store,sid,owner,counts,llm = local_session(mode="unknown")
    result = run(agent,store,sid,owner,"帮我检查网络")
    assert "你希望检查哪个诊断对象" in result.answer
    assert not llm.calls and sum(counts.values()) == 0


def test_report_meta_history_keep_zero_network_tools():
    agent,store,sid,owner,counts,llm = local_session()
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    for message in ("生成运维报告", "你没有回答我的问题", "分析我的诊断历史"):
        result = run(agent,store,sid,owner,message)
        assert not any(step.execution_scope != "target_neutral" for step in result.steps)
    assert sum(counts.values()) == 0


def test_dt05_mock_still_executes_but_cannot_claim_real_host():
    from netpilot.agent import AgentOrchestrator, SessionStore
    from target_helpers import TargetLLM
    from uuid import uuid4
    _,registry,counts = registry_and_counts("mock")
    store,owner = SessionStore(provider_kind="mock",environment_client_mode="mock"),uuid4()
    sid = store.create(owner).session_id
    agent = AgentOrchestrator(TargetLLM(),registry)
    result = run(agent,store,sid,owner,"我的电脑 DNS 异常，请调用 dns_lookup")
    assert result.diagnostic_target.subject == "mock_client"
    assert counts["dns_lookup"] == 1
    assert result.steps[0].target_subject == "mock_client" and result.steps[0].execution_scope == "mock_target"
    assert "Mock 模拟终端" in result.answer and "不代表真实校园网络" in result.answer
    run(agent,store,sid,owner,"检查这台 NetPilot 服务器的 DNS")
    assert counts["dns_lookup"] == 1
