import pytest

from netpilot.agent.intent import classify_turn_intent
from netpilot.conversation_context.models import ContextAcquisitionState
from netpilot.conversation_context.needs import assess_environment_need
from netpilot.environment import EnvironmentProfile, extract_environment_updates, merge_environment


def assess(message, **options):
    environment = merge_environment(EnvironmentProfile(), extract_environment_updates(message).model_dump(exclude_unset=True), source="user")
    return assess_environment_need(classify_turn_intent(message).intent, message, environment, ContextAcquisitionState(), **options)


@pytest.mark.parametrize("message", ["天津大学 VPN 怎么使用？", "eduroam 是什么？", "校园网账号怎么认证？", "IPv6 是什么？", "怎么下载 VPN 客户端？", "校园网客服电话是什么？"])
def test_tc01_knowledge_does_not_require_environment(message):
    assert not assess(message).required


def test_platform_specific_install_only_requires_os():
    result = assess("VPN 客户端怎么安装？")
    assert result.required_fields == result.missing_fields == ["os_family"]


def test_scope_then_relevant_network_and_vpn_only():
    assert assess("网页打不开").missing_fields == ["affected_scope"]
    assert assess("校园网连上但是没网").missing_fields == ["affected_scope", "network_access"]
    assert assess("VPN 一直失败").missing_fields == ["affected_scope", "vpn_enabled"]
    assert assess("VPN 连接失败").missing_fields == ["affected_scope", "vpn_enabled"]
    assert "os_family" not in assess("网页打不开").required_fields


def test_tc03_complete_message_has_no_redundant_question():
    result = assess("我用 Windows 11，连校园 WiFi，微信正常，但是网页打不开。")
    assert result.missing_fields == []


def test_known_evidence_and_explicit_host_check_do_not_restart_questionnaire():
    assert not assess("网页打不开", has_evidence=True).required
    assert not assess("请检查服务主机 DNS").required
    assert not assess("请调用 dns_lookup 检查网页打不开的原因").required


@pytest.mark.parametrize("message", ["如果一个同学用 Windows 连校园 WiFi，网页打不开怎么办？", "我是不是开着 VPN 才导致网页打不开？"])
def test_tc09_tc10_uncertain_questions_do_not_set_facts(message):
    assert not extract_environment_updates(message).model_fields_set


def test_clash_is_explicit_proxy_not_vpn():
    update = extract_environment_updates("我开着 Clash")
    assert update.proxy_enabled is True and "vpn_enabled" not in update.model_fields_set
