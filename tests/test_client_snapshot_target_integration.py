from uuid import uuid4
import pytest
from client_snapshot_helpers import payload, import_snapshot
from target_helpers import local_session, run
from netpilot.agent import SessionStore
from netpilot.agent.context_builder import build_task_context_message
from netpilot.agent.intent import TurnIntent
from netpilot.agent.target_capabilities import evaluate_target_capabilities


def test_cs02_capability_remains_fail_closed_even_with_snapshot():
    agent, store, sid, owner, counts, _ = local_session()
    task, _, _ = import_snapshot(store,sid,owner)
    cap = evaluate_target_capabilities(task.diagnostic_target,"local",has_client_snapshot_evidence=True)
    assert cap.can_use_client_snapshot_evidence and cap.can_use_target_neutral_tools
    assert not cap.can_use_host_network_tools
    assert not cap.allows_scope("client_snapshot")  # never an executable tool scope
    for name in counts:
        denied=agent.registry.execute(name,"{}",target=task.diagnostic_target)
        assert denied.result.error.code.value == "security_blocked"
    for message in ["检查我的电脑 DNS", "生成诊断报告", "给我下一步操作建议"]:
        result = run(agent,store,sid,owner,message)
        assert not result.steps and "快照" in result.answer
    assert sum(counts.values()) == 0


def test_cs12_replacement_archives_old_evidence_without_target_version_bump():
    agent, store, sid, owner, _, _ = local_session()
    first, _, _ = import_snapshot(store,sid,owner)
    second, duplicate, events = import_snapshot(store,sid,owner,payload("dns_failure"))
    assert not duplicate and events
    assert second.snapshot_sequence == 2 and second.diagnostic_target.target_version == 1
    assert len(second.evidence) == 10 and len(second.reusable_evidence()) == 5
    assert all(item.superseded for item in second.evidence if item.snapshot_id == first.client_snapshot_id)
    assert second.turn_index == 0 and not store.history(sid,owner)
    assert len({item.evidence_id for item in second.evidence}) == 10


def test_task_and_target_changes_do_not_reuse_old_client_facts():
    agent, store, sid, owner, _, _ = local_session()
    value = payload()
    task, _, _ = import_snapshot(store,sid,owner,value)
    store.advance_task_version(sid,owner)
    assert not store.task_state(sid,owner).reusable_evidence()
    task, duplicate, _ = import_snapshot(store,sid,owner,value)
    assert not duplicate and task.snapshot_sequence == 2
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    assert not store.task_state(sid,owner).reusable_evidence()
    store.update_diagnostic_target(sid,owner,"user_client")
    assert not store.task_state(sid,owner).reusable_evidence()
    task, duplicate, _ = import_snapshot(store,sid,owner,value)
    assert not duplicate and task.diagnostic_target.target_version == 3


def test_cs17_snapshot_environment_precedence_and_minimal_context():
    agent, store, sid, owner, _, _ = local_session()
    store.update_environment(sid,owner,{"os_family":"linux"},source="browser")
    task, _, _ = import_snapshot(store,sid,owner)
    assert task.environment_profile.os_family == "windows"
    assert task.environment_profile.field_sources["os_family"].source == "snapshot"
    assert task.environment_profile.field_sources["os_family"].confidence == "high"
    assert task.environment_profile.network_access == "unknown"
    assert task.environment_profile.proxy_enabled is None
    store.update_environment(sid,owner,{"os_family":"macos","os_version":"14"},source="user")
    task, _, _ = import_snapshot(store,sid,owner,payload("dns_failure"))
    assert task.environment_profile.os_family == "macos" and task.environment_profile.os_version == "14"
    message = build_task_context_message(user_message="分析",intent=TurnIntent.ANALYZE_EXISTING,task_version=1,evidence=task.reusable_evidence(),diagnostic_target=task.diagnostic_target)
    assert "CLIENT DIAGNOSTIC SNAPSHOT" in message.content and "CURRENT TARGET EVIDENCE" in message.content
    assert "ipv4_addresses" not in message.content and "hostname" not in message.content
    executed = message.content.split("ALREADY EXECUTED TOOLS")[1].split("USER ENVIRONMENT")[0]
    assert "client_snapshot.network_config(" not in executed


def test_user_os_without_version_never_gets_a_windows_version_for_macos():
    _, store, sid, owner, _, _ = local_session()
    store.update_environment(sid,owner,{"os_family":"macos"},source="user")
    task,_,_=import_snapshot(store,sid,owner)
    assert task.environment_profile.os_family == "macos" and task.environment_profile.os_version is None


def test_state_changed_turn_invalidates_snapshot_applicability():
    agent, store, sid, owner, counts, _=local_session()
    import_snapshot(store,sid,owner)
    result=run(agent,store,sid,owner,"重新检查我的电脑网络")
    assert result.task_version_advanced
    assert result.diagnostic_target.limitation_code == "remote_client_not_directly_observable"
    task=store.task_state(sid,owner)
    assert not task.client_snapshot_summary.applicable
    assert not task.reusable_evidence() and sum(counts.values()) == 0


def test_mock_and_host_do_not_accept_client_upload_and_archive_is_bounded():
    for kind, mode in [("mock","mock"),("local","remote_browser")]:
        store = SessionStore(provider_kind=kind,environment_client_mode=mode)
        owner=uuid4(); sid=store.create(owner).session_id
        if kind == "local": store.update_diagnostic_target(sid,owner,"netpilot_host")
        with pytest.raises(ValueError): import_snapshot(store,sid,owner)
    from netpilot.agent.session import SessionCapacityError
    store=SessionStore(provider_kind="local",environment_client_mode="remote_browser",max_evidence_records=7)
    owner=uuid4(); sid=store.create(owner).session_id
    import_snapshot(store,sid,owner)
    with pytest.raises(SessionCapacityError): import_snapshot(store,sid,owner,payload("dns_failure"))
    assert store.task_state(sid,owner).snapshot_sequence == 1


def test_snapshot_import_respects_trace_disabled():
    store=SessionStore(provider_kind="local",environment_client_mode="remote_browser",reasoning_trace_enabled=False)
    owner=uuid4();sid=store.create(owner).session_id
    task,_,events=import_snapshot(store,sid,owner)
    assert len(task.evidence) == 5 and not task.reasoning_trace and not events
