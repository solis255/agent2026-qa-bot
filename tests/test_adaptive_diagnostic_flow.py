"""Production Chat/SSE/session paths, capability boundary and priority regressions."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from client_snapshot_helpers import import_snapshot, payload, upload
from target_helpers import local_session, run
from test_context_acquisition import context_app, send, complete_sse

WINDOWS_WEB = "我用 Windows，连接校园 WiFi，微信正常，但是所有网页打不开。"


def test_remote_windows_requires_evidence_without_llm_or_host_handlers(context_app):
    app, client, owner, sid, tools, llm = context_app
    result = send(client,sid,WINDOWS_WEB)
    readiness = result["diagnostic_readiness"]
    assert (readiness["state"],readiness["recommended_action"]) == ("need_client_evidence","request_client_evidence")
    assert readiness["client_evidence_supported"] is True
    assert result["metrics"]["network_tool_calls"] == 0 and not result["client_evidence"]
    assert not llm.calls and tools.handler_calls == 0
    assert any(s["title"].startswith("诊断准备度：") for s in result["reasoning_trace"])
    assert app.state.sessions.task_state(UUID(sid),owner).last_diagnostic_readiness.model_dump(mode="json") == readiness
    assert client.get(f"/api/session/{sid}").json()["diagnostic_readiness"] == readiness


def test_scope_then_os_question_and_unknown_not_repeated(context_app):
    _,client,_,sid,tools,llm=context_app
    first=send(client,sid,"网络有问题")
    assert first["diagnostic_readiness"]["state"] == "need_context" and first["ui_action"]["field"] == "affected_scope"
    second=send(client,sid,"其他应用也不能联网",context_answer={"field":"affected_scope","value":"all_network"})
    assert second["ui_action"]["field"] == "os_family" and second["diagnostic_readiness"]["missing_context_fields"] == ["os_family"]
    third=send(client,sid,"不清楚",context_answer={"field":"os_family","value":"unknown"})
    assert third["ui_action"] is None and third["diagnostic_readiness"]["recommended_action"] == "continue_with_limitations"
    assert tools.handler_calls == 0


def test_single_service_then_explicit_dns_and_os_reply_preserves_check(context_app):
    _,client,_,sid,tools,_=context_app
    first=send(client,sid,"只有 GitHub 打不开，百度正常")
    assert first["diagnostic_readiness"]["recommended_action"] == "continue_with_limitations"
    second=send(client,sid,"那帮我检查我的 DNS")
    assert second["ui_action"]["field"] == "os_family"
    third=send(client,sid,"Windows",context_answer={"field":"os_family","value":"windows"})
    assert third["diagnostic_readiness"]["state"] == "need_client_evidence"
    assert tools.handler_calls == 0


def test_macos_has_no_inapplicable_collector_instructions(context_app):
    _,client,_,sid,tools,llm=context_app
    result=send(client,sid,WINDOWS_WEB.replace("Windows","macOS"))
    assert result["diagnostic_readiness"]["client_evidence_supported"] is False
    assert result["diagnostic_readiness"]["recommended_action"] == "continue_with_limitations"
    assert "PowerShell" not in result["answer"] and ".ps1" not in result["answer"]
    assert not llm.calls and tools.handler_calls == 0


def test_fresh_snapshot_analyzed_without_repeat_collection_or_host_tools(context_app):
    _,client,_,sid,tools,_=context_app
    send(client,sid,WINDOWS_WEB)
    assert upload(client,sid,payload("dns_failure")).status_code == 200
    result=send(client,sid,"请根据已有证据分析网页打不开")
    assert result["diagnostic_readiness"]["recommended_action"] == "analyze_existing"
    assert result["diagnostic_readiness"]["has_usable_client_evidence"]
    assert result["diagnostic_target"]["limitation_code"] == "client_snapshot_available"
    assert "采集时存在 DNS 解析失败" in result["answer"]
    assert tools.handler_calls == 0


@pytest.mark.parametrize("age", [-60,60])
def test_stale_or_clock_skew_snapshot_is_not_current(context_app, age):
    _,client,_,sid,tools,_=context_app
    send(client,sid,WINDOWS_WEB)
    value=payload(); value["generated_at"]=(datetime.now(timezone.utc)+timedelta(minutes=age)).isoformat()
    assert upload(client,sid,value).status_code == 200
    result=send(client,sid,"检查我的 DNS")
    assert result["diagnostic_readiness"]["state"] == "need_client_evidence"
    assert not result["diagnostic_readiness"]["has_usable_client_evidence"]
    assert result["diagnostic_target"]["limitation_code"] == "remote_client_not_directly_observable"
    assert result["client_evidence"] and tools.handler_calls == 0


@pytest.mark.parametrize("message", ["生成当前诊断报告", "查看我的诊断历史", "已经恢复了", "请求人工支持", "给我修复步骤", "你刚才重复了"])
def test_special_actions_are_not_blocked(context_app,message):
    _,client,_,sid,tools,_=context_app
    send(client,sid,WINDOWS_WEB)
    result=send(client,sid,message)
    assert result["diagnostic_readiness"] is None
    assert result["ui_action"] is None and result["metrics"]["network_tool_calls"] == 0
    assert tools.handler_calls == 0


def test_chat_sse_equivalent_readiness_and_persisted_history(context_app):
    app,client,owner,sid,_,_=context_app
    other=client.post("/api/session").json()["session_id"]
    plain=send(client,sid,WINDOWS_WEB)
    streamed=complete_sse(client.post("/api/chat/stream",json={"session_id":other,"message":WINDOWS_WEB}))
    assert plain["diagnostic_readiness"] == streamed["diagnostic_readiness"]
    assert plain["answer"] == streamed["answer"]
    for field in ["environment_profile","diagnostic_target"]:
        assert {k:v for k,v in plain[field].items() if k != "updated_at"} == {k:v for k,v in streamed[field].items() if k != "updated_at"}
    record=app.state.diagnosis_repository.get(owner,UUID(plain["record_id"]))
    assert record.diagnostic_readiness.model_dump(mode="json") == plain["diagnostic_readiness"] and record.schema_version == 12


@pytest.mark.parametrize("message", ["那怎么办？","下一步呢？"])
def test_repeated_evidence_notice_is_short(context_app,message):
    _,client,_,sid,_,_=context_app
    first=send(client,sid,WINDOWS_WEB)
    second=send(client,sid,message)
    assert second["diagnostic_readiness"]["state"] == "need_client_evidence"
    assert len(second["answer"]) < len(first["answer"]) and "证据不足" in second["answer"]


def test_host_and_existing_evidence_precedence_and_registry_still_denies_remote():
    agent,store,sid,owner,counts,llm=local_session()
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    first=run(agent,store,sid,owner,"检查 DNS")
    assert first.diagnostic_readiness.recommended_action == "run_allowed_diagnostics" and counts["dns_lookup"] == 1
    second=run(agent,store,sid,owner,"检查 DNS")
    assert second.diagnostic_readiness.recommended_action == "analyze_existing" and counts["dns_lookup"] == 1
    store.update_diagnostic_target(sid,owner,"user_client")
    forged=second.diagnostic_readiness.model_copy(update={"state":"ready","can_use_host_network_tools":True})
    assert forged.state == "ready"
    target=store.task_state(sid,owner).diagnostic_target
    assert agent.registry.execute("dns_lookup",'{"domain":"example.com"}',target=target).result.error.code.value == "security_blocked"
    assert counts["dns_lookup"] == 1


def test_recheck_os_question_is_bound_to_new_task_version(context_app):
    app,client,owner,sid,tools,_=context_app
    send(client,sid,"只有 GitHub 打不开，百度正常")
    first=send(client,sid,"重新检查我的电脑 DNS")
    task=app.state.sessions.task_state(UUID(sid),owner)
    assert first["ui_action"]["field"] == "os_family" and task.task_version == 2
    assert task.context_acquisition.task_version == 2
    second=send(client,sid,"Windows",context_answer={"field":"os_family","value":"windows"})
    assert second["diagnostic_readiness"]["state"] == "need_client_evidence"
    assert app.state.sessions.task_state(UUID(sid),owner).task_version == 2 and tools.handler_calls == 0


def test_upload_and_expiration_invalidate_cached_availability(context_app):
    app,client,owner,sid,_,_=context_app
    send(client,sid,WINDOWS_WEB)
    upload(client,sid,payload())
    assert client.get(f"/api/session/{sid}").json()["diagnostic_readiness"] is None
    send(client,sid,"检查我的 DNS")
    live=app.state.sessions._sessions[UUID(sid)].task_state
    for item in live.evidence:
        item.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    refreshed=client.get(f"/api/session/{sid}").json()
    assert refreshed["diagnostic_readiness"] is None
    assert refreshed["diagnostic_target"]["limitation_code"] == "remote_client_not_directly_observable"


def test_knowledge_then_fault_still_asks_scope(context_app):
    _,client,_,sid,_,_=context_app
    result=send(client,sid,"eduroam 是什么？")
    assert result["diagnostic_readiness"]["state"] == "knowledge_only"
    assert send(client,sid,"网页打不开")["ui_action"]["field"] == "affected_scope"


def test_legacy_persisted_snapshot_without_readiness(context_app):
    import json
    import sqlite3
    app,client,owner,sid,_,_=context_app
    response=send(client,sid,WINDOWS_WEB)
    with sqlite3.connect(app.state.settings.diagnosis_db_path) as db:
        raw=json.loads(db.execute("SELECT snapshot_json FROM diagnosis_records").fetchone()[0])
        raw.pop("diagnostic_readiness")
        raw["schema_version"]=11
        db.execute("UPDATE diagnosis_records SET snapshot_json=?",(json.dumps(raw),))
    assert app.state.diagnosis_repository.get(owner,UUID(response["record_id"])).diagnostic_readiness is None


@pytest.mark.parametrize("failure",["不能联网","无法联网"])
def test_all_applications_fault_is_recognized_through_real_extractor(context_app,failure):
    _,client,_,sid,tools,_=context_app
    result=send(client,sid,"我用 Windows，所有应用都"+failure+"。")
    assert result["environment_profile"]["affected_scope"] == "all_network"
    assert result["diagnostic_readiness"]["state"] == "need_client_evidence"
    assert result["ui_action"] is None and tools.handler_calls == 0


def test_uncollectable_gap_does_not_request_same_snapshot_again(context_app):
    _,client,_,sid,tools,_=context_app
    send(client,sid,WINDOWS_WEB)
    upload(client,sid,payload())
    result=send(client,sid,"所有网页打不开，请完整排查")
    assert result["diagnostic_readiness"]["reason"] == "collector_cannot_fill_remaining_gap"
    assert "重新采集上传" not in result["answer"] and "采集器无法" in result["answer"]
    assert tools.handler_calls == 0


def test_sufficient_evidence_denies_new_tool_arguments():
    from netpilot.llm import ChatResult, FunctionCall, ToolCall
    agent,store,sid,owner,counts,llm=local_session()
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    run(agent,store,sid,owner,"检查 DNS")
    def attempt_new(messages,**options):
        if options.get("tool_choice") == "none":
            return ChatResult(content="仅依据已有观察，未运行新检测。",model="test",duration_ms=0)
        return ChatResult(model="test",duration_ms=0,tool_calls=[ToolCall(id="new-dns",function=FunctionCall(name="dns_lookup",arguments='{"domain":"example.org"}'))])
    llm.chat=attempt_new
    result=run(agent,store,sid,owner,"检查 DNS")
    assert result.diagnostic_readiness.recommended_action == "analyze_existing"
    assert not result.steps and counts["dns_lookup"] == 1


@pytest.mark.parametrize("channel",["chat","advanced_form"])
def test_environment_updates_invalidate_previous_platform_decision(context_app,channel):
    app,client,owner,sid,_,_=context_app
    first=send(client,sid,WINDOWS_WEB)
    if channel == "chat":
        result=send(client,sid,"我现在改用 macOS 了")
        assert result["diagnostic_readiness"] is None
    else:
        assert client.patch("/api/session/environment/user",json={"session_id":sid,"os_family":"macos"}).status_code == 200
    assert client.get(f"/api/session/{sid}").json()["diagnostic_readiness"] is None
    assert app.state.diagnosis_repository.get(owner,UUID(first["record_id"])).diagnostic_readiness is None
