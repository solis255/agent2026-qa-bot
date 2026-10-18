from target_helpers import local_session, run


def test_dt07_host_client_host_switch_retains_archive_but_never_reuses_old_evidence():
    agent,store,sid,owner,counts,llm = local_session()
    first = run(agent,store,sid,owner,"检查 NetPilot 服务器的 DNS，调用 dns_lookup")
    state = store.task_state(sid,owner)
    old_id = state.evidence[0].evidence_id
    assert state.evidence[0].target_subject == "netpilot_host"
    old_version = state.diagnostic_target.target_version
    store.update_diagnostic_target(sid,owner,"user_client")
    changed = store.task_state(sid,owner)
    assert changed.diagnostic_target.target_version == old_version + 1
    assert changed.evidence[0].evidence_id == old_id
    assert changed.reusable_evidence() == []
    assert changed.coverage.checked_names() == []
    assert not changed.hypotheses and not changed.executed_tool_signatures
    assert changed.task_version == state.task_version
    result = run(agent,store,sid,owner,"我的 DNS 正常吗？")
    assert "尚未直接读取" in result.answer
    assert "DNS 正常" not in result.answer
    assert result.steps == [] and counts["dns_lookup"] == 1
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    run(agent,store,sid,owner,"调用 dns_lookup 检查 github.com")
    assert counts["dns_lookup"] == 2
    assert old_id not in {r.evidence_id for r in store.task_state(sid,owner).reusable_evidence()}


def test_switch_filters_old_text_history_as_well_as_structured_memory():
    agent,store,sid,owner,counts,llm = local_session()
    run(agent,store,sid,owner,"检查 NetPilot 服务器的 DNS，调用 dns_lookup")
    store.update_diagnostic_target(sid,owner,"user_client")
    assert store.history(sid,owner)  # Full audit transcript is preserved.
    assert store.begin_turn(sid,owner) == []
    store.abort_turn(sid)
    result = run(agent,store,sid,owner,"基于刚才结果继续分析，不要重新检测")
    assert not result.reused_evidence_ids and not result.steps
    assert "不能据旧对象" in result.answer


def test_dt14_target_trace_initialization_switch_and_limit_not_repeated():
    agent,store,sid,owner,counts,llm = local_session()
    first = run(agent,store,sid,owner,"我的电脑打不开网页，帮我检查")
    assert sum(s.title == "确认诊断对象" for s in first.reasoning_trace) == 1
    assert sum(s.title == "限制不适用的检测" for s in first.reasoning_trace) == 1
    second = run(agent,store,sid,owner,"我的电脑 DNS 正常吗")
    assert not any(s.title in {"确认诊断对象","限制不适用的检测"} for s in second.reasoning_trace)
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    third = run(agent,store,sid,owner,"调用 dns_lookup")
    assert sum(s.title == "切换诊断对象" for s in third.reasoning_trace) == 1


def test_natural_language_switch_to_my_computer_cannot_keep_host_claims():
    agent,store,sid,owner,counts,llm = local_session()
    host = run(agent,store,sid,owner,"我要检查 NetPilot 服务器的 DNS，请调用 dns_lookup")
    client = run(agent,store,sid,owner,"我的电脑上不了网，帮我检查")
    assert client.diagnostic_target.subject == "user_client" and client.diagnostic_target.source == "user"
    assert client.diagnostic_target.target_version == host.diagnostic_target.target_version + 1
    assert not client.steps and not client.reused_evidence_ids and counts["dns_lookup"] == 1
    assert store.task_state(sid,owner).reusable_evidence() == []


def test_presenter_defensively_excludes_mismatched_host_steps_from_client_diagnosis():
    from netpilot.api.presenters import present_chat
    agent,store,sid,owner,counts,llm = local_session()
    host = run(agent,store,sid,owner,"检查 NetPilot 服务器的 DNS，调用 dns_lookup")
    target = store.update_diagnostic_target(sid,owner,"user_client")
    # Simulate a stale internal result; the actual Orchestrator never creates this.
    stale = host.model_copy(update={"diagnostic_target":target})
    response = present_chat(sid,stale)
    assert response.diagnosis.evidence == []
    assert response.tool_calls[0].target_subject == "netpilot_host"
