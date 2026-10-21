import pytest

from netpilot.environment import EnvironmentProfile, extract_environment_updates, merge_environment
from netpilot.conversation_context.acquisition import acquire_context
from netpilot.conversation_context.models import ContextAcquisitionState
from netpilot.conversation_context.questions import free_text_answer


@pytest.mark.parametrize("message,family,version", [
    ("我用 Windows 11", "windows", "11"), ("我使用 Windows", "windows", None),
    ("我现在用 Win11", "windows", "11"), ("我的电脑是 Windows", "windows", None),
    ("我用 Mac", "macos", None), ("我用 Mac 系统", "macos", None), ("我用 Mac系统", "macos", None),
    ("我使用的是macos", "macos", None), ("我现在用 macOS", "macos", None),
    ("我的电脑是 MacBook", "macos", None), ("我换成 Mac 了", "macos", None),
    ("我现在改用 Mac 了", "macos", None), ("我从 Windows 换成 Mac 了", "macos", None),
    ("我原来用 Windows，现在改用 Mac 了", "macos", None),
    ("我之前用 Mac，现在换成 Windows 11", "windows", "11"),
    ("我用 Linux", "linux", None), ("我现在换成 Ubuntu", "linux", None),
])
def test_current_and_transition_os_aliases(message, family, version):
    update = extract_environment_updates(message)
    assert update.os_family == family and update.os_version == version


@pytest.mark.parametrize("message,access", [
    ("我连校园 WiFi", "campus_wifi"), ("我连校园无线", "campus_wifi"),
    ("我现在用 WiFi", "campus_wifi"), ("我现在连无线网", "campus_wifi"),
    ("我换成 WiFi 了", "campus_wifi"), ("我改用无线了", "campus_wifi"),
    ("我从有线换到 WiFi", "campus_wifi"), ("我从有线网换成 WiFi 了", "campus_wifi"),
    ("我连校园有线", "campus_wired"), ("我连校园网线", "campus_wired"),
    ("我连有线网", "campus_wired"), ("我用有线网络", "campus_wired"),
    ("我现在插网线", "campus_wired"), ("我现在用网线", "campus_wired"),
    ("我改用有线网了", "campus_wired"), ("我切换到有线网络了", "campus_wired"),
    ("我换成网线了", "campus_wired"), ("我从 WiFi 换到有线了", "campus_wired"),
    ("我从 WiFi 换成有线网了", "campus_wired"), ("之前用 WiFi，现在改用有线", "campus_wired"),
    ("我现在在家里，用有线网。", "off_campus"), ("我在家里接有线网", "off_campus"),
    ("我现在在校外，用家里的网线", "off_campus"), ("我现在连校园有线网", "campus_wired"),
    ("我改用手机热点了", "mobile_hotspot"), ("我现在改为移动热点", "mobile_hotspot"),
])
def test_network_aliases_destination_wins_and_off_campus_priority(message, access):
    assert extract_environment_updates(message).network_access == access


@pytest.mark.parametrize("message", [
    "我的 MAC 地址是多少？", "网卡 MAC 地址异常", "我的 MAC 地址好像有问题。", "我用 MAC address 查询工具",
    "如果一个同学用 Mac 连校园 WiFi，网页打不开怎么办？", "我同学用 Mac，我自己用 Windows。",
    "我同学用 Mac 连校园 WiFi。", "是不是 Mac 更容易断网？", "我是不是应该换成有线网？",
    "我准备换成 Mac", "我打算改用有线", "我想接网线", "我准备改用有线网。",
    "我不使用 Windows", "我没连接校园 WiFi", "我没有用校园有线网络", "我没有换成 Mac",
    "之前用 Windows", "原来用校园 WiFi", "我用 Mac 还是 Windows？",
])
def test_unconfirmed_planned_third_party_historical_or_mac_identifiers_are_not_facts(message):
    assert extract_environment_updates(message).model_dump(exclude_unset=True) == {}


@pytest.mark.parametrize("message", ["Mac", "Mac系统", "Mac 系统", "macOS", "苹果电脑", "Win11", "Windows 11"])
def test_pending_os_short_answer_allowlist(message):
    answer = free_text_answer("os_family", message)
    assert answer.value == ("windows" if message in {"Win11", "Windows 11"} else "macos")


@pytest.mark.parametrize("message,access", [
    ("WiFi","campus_wifi"), ("校园 WiFi","campus_wifi"), ("无线","campus_wifi"), ("无线网","campus_wifi"),
    ("有线","campus_wired"), ("有线网","campus_wired"), ("网线","campus_wired"), ("校园有线","campus_wired"),
    ("校园网线","campus_wired"), ("手机热点","mobile_hotspot"), ("校外","off_campus"),
])
def test_pending_network_short_answer_allowlist(message, access):
    assert free_text_answer("network_access", message).value == access


def test_changes_are_post_merge_and_enrichment_does_not_advance():
    initial = acquire_context("我用 Windows 11，连校园 WiFi", EnvironmentProfile(), ContextAcquisitionState())
    assert initial.changed_fields["os_family"] == ("unknown", "windows")
    assert not initial.environment_transition
    changed = acquire_context("我换成 Mac 了", initial.environment, initial.state)
    assert changed.changed_fields["os_family"] == ("windows", "macos")
    assert changed.changed_fields["os_version"] == ("11", None)
    assert changed.environment_transition
    assert changed.environment.os_version is None
    assert changed.classification.intent.value == "state_changed"


@pytest.mark.parametrize("field,initial,message", [("vpn_enabled",False,"我开着 VPN"), ("proxy_enabled",True,"我关闭了代理")])
def test_boolean_known_changes_are_transitions_and_none_is_unknown(field, initial, message):
    env = merge_environment(EnvironmentProfile(), {field:initial}, source="user")
    result = acquire_context(message, env, ContextAcquisitionState())
    assert result.changed_fields[field] == (initial, not initial) and result.environment_transition


def test_same_value_and_scope_update_are_not_key_environment_transitions():
    env = merge_environment(EnvironmentProfile(), {"os_family":"windows","affected_scope":"single_service"}, source="user")
    same = acquire_context("我用 Windows，只有网页打不开", env, ContextAcquisitionState())
    assert same.changed_fields == {"affected_scope":("single_service","web_only")}
    assert not same.environment_transition


@pytest.mark.parametrize("message", ["根据天津大学知识库解释 VPN。", "eduroam 是什么？", "VPN 客户端怎么安装？", "校园网代理配置方法"])
def test_topic_mention_is_not_a_pure_environment_update(message):
    from netpilot.environment import is_environment_update_only
    assert not is_environment_update_only(message)


@pytest.mark.parametrize("version", ["1" * 40, "١١"])
def test_unrepresentable_version_does_not_break_extraction_or_relax_schema(version):
    from pydantic import ValidationError
    from netpilot.environment import EnvironmentUpdate
    update = extract_environment_updates("我用 Windows " + version)
    assert update.os_family == "windows" and update.os_version is None
    with pytest.raises(ValidationError): EnvironmentUpdate(os_version=version)


def test_acquisition_can_be_imported_before_agent_package():
    import subprocess
    import sys
    result = subprocess.run([sys.executable,"-c","from netpilot.conversation_context.acquisition import acquire_context, environment_confirmation"],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stderr
