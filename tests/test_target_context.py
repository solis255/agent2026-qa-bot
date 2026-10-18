from netpilot.agent.context_builder import build_task_context_message
from netpilot.agent.intent import TurnIntent
from target_helpers import local_session, run


def test_dt11_context_drops_old_evidence_hypotheses_coverage_and_executed_tools():
    agent,store,sid,owner,counts,llm = local_session()
    run(agent,store,sid,owner,"检查 NetPilot 服务器的 DNS，调用 dns_lookup")
    prior = store.task_state(sid,owner)
    store.update_diagnostic_target(sid,owner,"user_client")
    target = store.task_state(sid,owner).diagnostic_target
    context = build_task_context_message(user_message="我的DNS正常吗",intent=TurnIntent.ANALYZE_EXISTING,task_version=1,
        evidence=prior.evidence,coverage=prior.coverage,hypotheses=prior.hypotheses,diagnostic_target=target).content
    assert "DIAGNOSTIC TARGET" in context and "Subject: user_client" in context
    assert "Direct system-level observation of subject: unavailable" in context
    assert "NORMAL EVIDENCE\n- none" in context
    assert "ALREADY EXECUTED TOOLS\n- none" in context
    assert prior.evidence[0].evidence_id not in context
    assert "coverage=none" in context


def test_no_old_host_claims_leak_into_remote_knowledge_finalization():
    agent,store,sid,owner,counts,llm = local_session(rag=True)
    run(agent,store,sid,owner,"检查 NetPilot 服务器的 DNS，调用 dns_lookup")
    store.update_diagnostic_target(sid,owner,"user_client")
    run(agent,store,sid,owner,"天津大学 VPN 怎么使用？请检索知识库并标出来源。")
    final_prompt = "\n".join(message.content or "" for message in llm.calls[-1][0])
    assert "Subject: user_client" in final_prompt
    assert "NetPilot 服务主机 DNS 正常" not in final_prompt
