from netpilot.agent.tool_signature import canonical_tool_signature
from target_helpers import local_session, run


def test_dt08_signatures_include_subject_and_target_version_but_rag_is_neutral():
    args = {"domain":"GitHub.COM."}
    host = canonical_tool_signature("dns_lookup",args,target_subject="netpilot_host",target_version=1)
    client = canonical_tool_signature("dns_lookup",args,target_subject="user_client",target_version=1)
    later = canonical_tool_signature("dns_lookup",args,target_subject="netpilot_host",target_version=3)
    assert len({host,client,later}) == 3
    assert host == 'netpilot_host:v1:dns_lookup:{"domain":"github.com"}'
    assert canonical_tool_signature("knowledge_search",{"query":"VPN"},target_subject="netpilot_host",target_version=1) == canonical_tool_signature("knowledge_search",{"query":"vpn"},target_subject="user_client",target_version=2)


def test_same_target_reuses_then_target_round_trip_reexecutes():
    agent,store,sid,owner,counts,llm = local_session()
    first = run(agent,store,sid,owner,"检查 NetPilot 服务器的 DNS，调用 dns_lookup")
    second = run(agent,store,sid,owner,"继续检查 DNS，调用 dns_lookup")
    assert counts["dns_lookup"] == 1 and not second.steps
    assert second.reused_evidence_ids == [first.steps[0].evidence_id]
    store.update_diagnostic_target(sid,owner,"user_client")
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    run(agent,store,sid,owner,"调用 dns_lookup 检查DNS")
    assert counts["dns_lookup"] == 2
