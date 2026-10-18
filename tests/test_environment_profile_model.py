import pytest
from pydantic import ValidationError

from netpilot.environment import EnvironmentProfile, BrowserEnvironmentValues, EnvironmentUpdate


def test_ep01_default_unknown_is_not_false_and_defaults_are_independent():
    first, second = EnvironmentProfile(), EnvironmentProfile()
    assert first.os_family == first.network_access == first.affected_scope == "unknown"
    assert first.client_mode == "unknown"
    assert first.vpn_enabled is first.proxy_enabled is first.browser_online is None
    assert first.effective_type is first.estimated_rtt_ms is first.estimated_downlink_mbps is None
    assert first.updated_at.tzinfo is not None
    first.field_sources["os_family"] = {"source": "user", "confidence": "high"}
    assert not second.field_sources


@pytest.mark.parametrize("values", [
    {"vpn_enabled": "false"}, {"proxy_enabled": 0}, {"os_family": "darwin"},
    {"os_version": "Mozilla/5.0"}, {"affected_service": "https://example.test?q=secret"},
    {"affected_service": "8.8.8.8"}, {"affected_service": "AA-BB-CC-DD-EE-FF"},
    {"affected_service": "SSID campus"}, {"affected_service": "token abc"},
    {"affected_service": "<script>oops</script>"},
])
def test_ep06_user_values_reject_sensitive_or_non_normalized_input(values):
    with pytest.raises(ValidationError):
        EnvironmentUpdate(**values)


@pytest.mark.parametrize("values", [
    {"vpn_enabled": False}, {"network_access": "campus_wifi"}, {"user_agent": "privateUA"},
    {"field_sources": {"os_family": {"source":"server", "confidence":"high"}}},
    {"estimated_rtt_ms": -1}, {"estimated_rtt_ms": 1.2}, {"estimated_downlink_mbps": float("inf")},
    {"estimated_downlink_mbps": True}, {"browser_language": "secret token"},
])
def test_browser_allowlist_and_strict_types(values):
    with pytest.raises(ValidationError):
        BrowserEnvironmentValues(**values)


def test_ep05_unsupported_connection_is_optional():
    browser = BrowserEnvironmentValues(browser_online=True, browser_language="zh-CN")
    assert browser.effective_type is browser.estimated_rtt_ms is browser.estimated_downlink_mbps is None
