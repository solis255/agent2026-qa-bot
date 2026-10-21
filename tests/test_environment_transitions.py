"""Regressions from the two real 13A conversations, through normal chat APIs."""
from uuid import UUID
from uuid import uuid4

import pytest

from test_context_acquisition import context_app, send, complete_sse
from netpilot.conversation_context.acquisition import acquire_context
from netpilot.conversation_context.models import ContextAcquisitionState
from netpilot.environment import EnvironmentProfile, merge_environment


def test_environment_can_change_from_windows_wifi_to_mac_wired(context_app):
    app, client, owner, sid, *_ = context_app
    first = send(client, sid, "网络有问题")
    assert first["ui_action"]["field"] == "affected_scope"
    send(client, sid, "只有某个网站或服务有问题")
    windows = send(client, sid, "我用 Windows 11，连校园 WiFi，微信正常，但是网页打不开。")
    profile = windows["environment_profile"]
    assert (profile["os_family"], profile["network_access"], profile["affected_scope"]) == ("windows", "campus_wifi", "web_only")
    assert profile["os_version"] == "11"
    changed = send(client, sid, "我用 Mac，连有线网，微信正常，但是网页打不开。")
    profile = changed["environment_profile"]
    assert (profile["os_family"], profile["network_access"], profile["affected_scope"]) == ("macos", "campus_wired", "web_only")
    assert profile["os_version"] is None
    assert profile["field_sources"]["os_family"]["source"] == profile["field_sources"]["network_access"]["source"] == "user"
    task = app.state.sessions.task_state(UUID(sid), owner)
    assert task.environment_profile.os_family == "macos"
    assert task.environment_profile.network_access == "campus_wired"
    assert client.get(f"/api/session/{sid}").json()["environment_profile"] == profile


def test_mac_system_alias_is_recognized_over_browser_windows(context_app):
    _, client, _, sid, *_ = context_app
    assert client.patch("/api/session/environment/browser", json={"session_id":sid,"os_family":"windows"}).status_code == 200
    result = send(client, sid, "我用 Mac系统，连有线网，微信正常，但是网页打不开。")
    profile = result["environment_profile"]
    assert (profile["os_family"], profile["network_access"], profile["affected_scope"]) == ("macos", "campus_wired", "web_only")
    assert client.patch("/api/session/environment/browser", json={"session_id":sid,"os_family":"windows"}).json()["os_family"] == "macos"


def test_environment_transition_phrase_updates_existing_user_value():
    profile = merge_environment(EnvironmentProfile(), {"network_access":"campus_wifi"}, source="user")
    result = acquire_context("我现在改用有线网了", profile, ContextAcquisitionState())
    assert result.environment.network_access == "campus_wired"
    assert result.changed_fields["network_access"] == ("campus_wifi", "campus_wired")
    assert result.environment_transition is True


@pytest.mark.parametrize("message,family,access", [("我现在改用有线网了","windows","campus_wired"), ("我换成 Mac 了","macos","campus_wifi")])
def test_old_snapshot_plan_and_verification_are_archived_after_real_change(context_app, message, family, access):
    from client_snapshot_helpers import payload, upload
    from netpilot.history import SQLiteDiagnosisRepository
    app, client, owner, sid, tools, _ = context_app
    send(client, sid, "我用 Windows 11，连校园 WiFi，微信正常，但是网页打不开。")
    assert upload(client, sid, payload("dns_failure")).status_code == 200
    send(client, sid, "请根据快照分析网页问题")
    assert client.post("/api/session/remediation-plan", json={"session_id":sid}).status_code == 200
    before = app.state.sessions.task_state(UUID(sid), owner)
    ids = {e.evidence_id for e in before.reusable_evidence()}
    assert ids and before.verification_cycles and before.remediation_plan
    result = send(client, sid, message)
    task = app.state.sessions.task_state(UUID(sid), owner)
    assert task.task_version == before.task_version + 1
    assert task.diagnostic_target.target_version == before.diagnostic_target.target_version
    assert (task.environment_profile.os_family,task.environment_profile.network_access) == (family,access)
    assert ids.issubset({e.evidence_id for e in task.evidence})
    assert all(e.superseded for e in task.evidence if e.evidence_id in ids)
    assert task.reusable_evidence() == [] and not task.hypotheses and not task.coverage.checked_names()
    assert task.client_snapshot_summary.applicable is False
    assert all(c.status == "superseded" for c in task.verification_cycles)
    assert task.remediation_plan.status == "superseded"
    assert result["client_snapshot_summary"]["applicable"] is False
    assert result["diagnosis"]["primary_issue"] in {"undetermined","insufficient_evidence"}
    assert tools.handler_calls == 0
    record = SQLiteDiagnosisRepository(app.state.settings.diagnosis_db_path).get(owner, UUID(result["record_id"]))
    assert ids.issubset({e.evidence_id for e in record.client_evidence})
    assert record.environment_profile == task.environment_profile
    followup = send(client, sid, "基于刚才结果继续分析，不要重新检测")
    assert followup["diagnosis"]["primary_issue"] in {"undetermined","insufficient_evidence"}
    assert not app.state.sessions.task_state(UUID(sid), owner).reusable_evidence()


def test_host_tool_evidence_is_retained_but_not_current():
    from netpilot.agent import SessionStore
    from reasoning_helpers import make_agent, run_session, CASE_A
    store, owner = SessionStore(), uuid4()
    sid = store.create(owner).session_id
    store.update_environment(sid, owner, {"network_access":"campus_wifi"}, source="user")
    agent = make_agent()
    run_session(agent, store, sid, owner, CASE_A)
    before = store.task_state(sid, owner)
    assert before.reusable_evidence()
    calls = len(agent.llm.calls)
    result = run_session(agent, store, sid, owner, "我现在改用有线网了")
    after = store.task_state(sid, owner)
    assert after.task_version == before.task_version + 1 and result.task_version_advanced
    assert len(after.evidence) == len(before.evidence) and not after.reusable_evidence()
    assert all(e.superseded for e in after.evidence)
    assert len(agent.llm.calls) == calls  # Pure context update never invokes the model.


def test_enrichment_and_idempotent_update_do_not_advance_or_ack_fake_change(context_app):
    app, client, owner, sid, _, llm = context_app
    original = app.state.sessions.task_state(UUID(sid), owner).task_version
    first = send(client, sid, "我现在改用有线网了")
    assert first["environment_profile"]["network_access"] == "campus_wired"
    assert app.state.sessions.task_state(UUID(sid), owner).task_version == original
    again = send(client, sid, "我现在改用有线网了")
    assert app.state.sessions.task_state(UUID(sid), owner).task_version == original
    assert all(term not in again["answer"] for term in ["已更新","已记录","已切换"])
    llm.answer = "已更新为银河系统，已切换网络。"  # Must never reach this untrusted model acknowledgement.
    for message in ["我现在改用神秘网络了", "我现在用银河系统", "我的接入方式是超光速网络"]:
        failed = send(client, sid, message)
        assert failed["environment_profile"] == again["environment_profile"]
        assert all(term not in failed["answer"] for term in ["已更新","已记录","已切换"])
    assert not llm.calls


def test_explicit_environment_ack_agrees_with_sse_session_history_and_report(context_app):
    app, client, owner, sid, *_ = context_app
    send(client, sid, "我用 Windows 11，连校园 WiFi，微信正常，但是网页打不开。")
    before = app.state.sessions.task_state(UUID(sid), owner)
    response = client.post("/api/chat/stream", json={"session_id":sid,"message":"我现在改用有线网了"})
    changed = complete_sse(response)
    assert "校园 WiFi" in changed["answer"] and "校园有线" in changed["answer"] and "已更新" in changed["answer"]
    assert changed["environment_profile"]["network_access"] == "campus_wired"
    after = app.state.sessions.task_state(UUID(sid), owner)
    assert after.task_version == before.task_version + 1
    assert after.context_acquisition.task_version == after.task_version
    history = client.get(f'/api/diagnoses/{changed["record_id"]}').json()
    assert history["environment_profile"] == changed["environment_profile"]
    assert history["conversation_turns"][-1]["assistant_answer"] == changed["answer"]
    report = client.get(f'/api/diagnoses/{changed["record_id"]}/report').json()
    assert report["environment_profile"] == changed["environment_profile"]


def test_environment_transition_and_recheck_advance_once(context_app):
    from netpilot.agent.intent import classify_turn_intent
    app, client, owner, sid, *_ = context_app
    send(client, sid, "我连校园 WiFi")
    before = app.state.sessions.task_state(UUID(sid), owner).task_version
    message = "我现在改用有线网了，重新检查"
    assert classify_turn_intent(message).force_recheck
    send(client, sid, message)
    assert app.state.sessions.task_state(UUID(sid), owner).task_version == before + 1


def test_tool_history_and_report_do_not_keep_old_environment_diagnosis_current(tmp_path):
    from fastapi.testclient import TestClient
    from conftest import register_test_user
    from reasoning_helpers import trace_app, CASE_A
    app = trace_app(tmp_path)
    with TestClient(app) as client:
        register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        send(client, sid, "我连校园 WiFi")
        diagnosed = send(client, sid, CASE_A)
        assert diagnosed["diagnosis"]["primary_issue"] == "dns_resolution_failure"
        old_ids = {call["evidence_id"] for call in diagnosed["tool_calls"]}
        changed = send(client, sid, "我现在改用有线网了")
        record = client.get(f'/api/diagnoses/{changed["record_id"]}').json()
        assert record["diagnosis"]["primary_issue"] in {"undetermined", "insufficient_evidence"}
        assert old_ids.issubset({call["evidence_id"] for call in record["tool_calls"]})
        report = client.get(f'/api/diagnoses/{changed["record_id"]}/report').json()
        assert report["diagnosis"]["primary_issue"] in {"undetermined", "insufficient_evidence"}
        assert not report["tool_calls"]
        assert old_ids.issubset({call["evidence_id"] for call in report["archived_tool_calls"]})
