import pytest
from pydantic import ValidationError

from netpilot.conversation_context.acquisition import acquire_context
from netpilot.conversation_context.models import ContextAcquisitionState, ContextAnswer
from netpilot.environment import EnvironmentProfile, merge_environment


def test_tc02_single_question_choices_no_raw_message_saved():
    result = acquire_context("网络有问题 token=private", EnvironmentProfile(), ContextAcquisitionState())
    assert result.question.field == "affected_scope"
    assert len(result.state.asked_fields) == 1
    assert any(c.value == "unknown" for c in result.question.choices)
    assert "private" not in result.state.model_dump_json()


def test_tc05_tc06_unknown_is_none_and_not_reasked():
    env = merge_environment(EnvironmentProfile(), {"affected_scope":"web_only"}, source="user")
    first = acquire_context("VPN 一直失败", env, ContextAcquisitionState())
    assert first.question.field == "vpn_enabled"
    second = acquire_context("我不知道。", first.environment, first.state)
    assert second.environment.vpn_enabled is None
    assert second.environment.field_sources["vpn_enabled"].source == "user"
    assert second.state.unknown_fields == ["vpn_enabled"]
    assert second.question is None
    third = acquire_context("还是打不开。", second.environment, second.state)
    assert third.question is None
    later = acquire_context("我刚确认，我开着 VPN", third.environment, third.state)
    assert later.environment.vpn_enabled is True
    assert not later.state.unknown_fields


def test_network_choice_resume_then_short_free_text_answers():
    first = acquire_context("校园网连不上", EnvironmentProfile(), ContextAcquisitionState())
    assert first.question.field == "affected_scope"
    second = acquire_context("也不能联网", first.environment, first.state)
    assert second.question.field == "network_access"
    third = acquire_context("校园 WiFi", second.environment, second.state)
    assert third.environment.network_access == "campus_wifi"
    assert third.environment.field_sources["network_access"].source == "user"
    assert third.question is None and third.classification.intent.value == "diagnose"
    assert third.state.last_question_field is None


def test_tc04_explicit_user_mac_survives_browser_update():
    env = merge_environment(EnvironmentProfile(), {"os_family":"windows"}, source="browser")
    result = acquire_context("我实际使用的是 macOS。", env, ContextAcquisitionState())
    assert result.environment.os_family == "macos"
    assert merge_environment(result.environment, {"os_family":"windows"}, source="browser") == result.environment


@pytest.mark.parametrize("field,value", [("api_key","secret"), ("network_access","../../etc/passwd"), ("vpn_enabled",False)])
def test_tc08_strict_answer_allowlist(field, value):
    with pytest.raises(ValidationError): ContextAnswer(field=field, value=value)


def test_tc12_old_state_defaults_and_extra_forbidden():
    state = ContextAcquisitionState.model_validate({})
    assert state.asked_fields == state.unknown_fields == [] and state.last_question_field is None
    with pytest.raises(ValidationError): ContextAcquisitionState(message="private")


def test_fresh_task_or_target_resets_question_suppression():
    first = acquire_context("网络有问题", EnvironmentProfile(), ContextAcquisitionState())
    unknown = acquire_context("不清楚", first.environment, first.state)
    fresh_env = EnvironmentProfile()
    again = acquire_context("网络有问题", fresh_env, unknown.state, task_version=2)
    assert again.question.field == "affected_scope" and again.state.task_version == 2
