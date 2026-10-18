from uuid import uuid4

import pytest

from netpilot.agent import SessionStore
from netpilot.environment import EnvironmentProfile, PRECEDENCE, extract_environment_updates, merge_environment
from reasoning_helpers import CASE_A, CASE_B, make_agent, run_session


@pytest.mark.parametrize("source", list(PRECEDENCE))
def test_precedence_all_sources(source):
    original = merge_environment(EnvironmentProfile(), {"os_family":"windows"}, source=source)
    for challenger in PRECEDENCE:
        result = merge_environment(original, {"os_family":"macos"}, source=challenger)
        assert result.os_family == ("macos" if PRECEDENCE[challenger] >= PRECEDENCE[source] else "windows")
    assert original.os_family == "windows"


def test_ep03_user_override_browser_and_no_heartbeat_change():
    profile = merge_environment(EnvironmentProfile(), {"os_family":"windows"}, source="browser")
    profile = merge_environment(profile, extract_environment_updates("我其实是 macOS").model_dump(exclude_unset=True), source="user")
    final = merge_environment(profile, {"os_family":"windows"}, source="browser")
    assert final == profile
    assert final.os_family == "macos"
    assert final.field_sources["os_family"].model_dump() == {"source":"user", "confidence":"high"}


@pytest.mark.parametrize("message", [
    "我的 Windows 11 笔记本连校园 WiFi 后微信正常，但网页打不开，我没开 VPN。",
    "我现在用 Windows 11，连校园 WiFi，没开 VPN，微信正常但网页打不开。",
])
def test_explicit_statement_only_updates_mentioned_fields(message):
    assert extract_environment_updates(message).model_dump(exclude_unset=True) == {
        "os_family":"windows", "network_access":"campus_wifi", "vpn_enabled":False, "affected_scope":"web_only",
    }


@pytest.mark.parametrize("message", ["如果我用 Windows，没开 VPN 会怎样？", "我想开启 VPN", "如何关闭代理？", "同学用 macOS，没开 VPN", "我不使用 Windows", "我没有关闭 VPN", "VPN 关闭会怎样", "我没连接校园 WiFi", "我没有用校园有线网络"])
def test_questions_hypotheticals_other_users_and_future_intentions_are_not_facts(message):
    assert extract_environment_updates(message).model_dump(exclude_unset=True) == {}


def test_ep04_missing_field_stays_unknown_and_explicit_reset_stays_none():
    profile = merge_environment(EnvironmentProfile(), {"vpn_enabled":False}, source="user")
    assert profile.vpn_enabled is False and profile.proxy_enabled is None
    reset = merge_environment(profile, {"vpn_enabled":None}, source="user")
    assert reset.vpn_enabled is None
    assert reset.field_sources["vpn_enabled"].source == "user"


def test_profile_update_preserves_evidence_task_version_and_trace_is_not_repeated():
    sessions, owner = SessionStore(), uuid4()
    sid = sessions.create(owner).session_id
    agent = make_agent()
    run_session(agent, sessions, sid, owner, CASE_A)
    before = sessions.task_state(sid, owner)
    sessions.update_environment(sid, owner, {"os_family":"windows"}, source="browser")
    after = sessions.task_state(sid, owner)
    assert before.evidence == after.evidence
    assert before.task_version == after.task_version == 1
    assert before.turn_index == after.turn_index == 1
    second = run_session(agent, sessions, sid, owner, CASE_B)
    third = run_session(agent, sessions, sid, owner, CASE_B)
    assert sum(s.title == "确认用户环境" for s in second.reasoning_trace) == 1
    assert not any(s.title == "确认用户环境" for s in third.reasoning_trace)
    assert third.environment_profile.os_family == "windows"
    # Bounded Trace eviction must not look like a new environment initialization.
    sessions._sessions[sid].task_state.reasoning_trace.clear()
    fourth = run_session(agent, sessions, sid, owner, CASE_B)
    assert not any(s.title == "确认用户环境" for s in fourth.reasoning_trace)


def test_os_change_drops_obsolete_version():
    profile = merge_environment(EnvironmentProfile(), {"os_family":"windows", "os_version":"11"}, source="user")
    changed = merge_environment(profile, {"os_family":"macos"}, source="user")
    assert changed.os_version is None and "os_version" not in changed.field_sources


def test_scopes_are_explicit_not_inferred_from_negated_application_health():
    assert extract_environment_updates("微信不正常，但网页打不开").affected_scope == "unknown"
    assert extract_environment_updates("只有校内资源无法访问").affected_scope == "internal_resource"
    update = extract_environment_updates("只有 github.com 打不开")
    assert update.affected_scope == "single_service" and update.affected_service == "github.com"
    assert extract_environment_updates("只有 8.8.8.8 连不上").affected_service is None


def test_vpn_statements_are_not_commands_and_do_not_guess_proxy():
    for message in ("开启 VPN", "请开启 VPN", "我想开启 VPN"):
        assert extract_environment_updates(message).vpn_enabled is None
    assert extract_environment_updates("我未使用 VPN").vpn_enabled is False
    assert extract_environment_updates("我关闭了 VPN").vpn_enabled is False
    assert extract_environment_updates("我打开了 VPN").vpn_enabled is True
    assert extract_environment_updates("我开启 VPN").proxy_enabled is None
