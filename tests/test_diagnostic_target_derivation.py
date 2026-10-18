import pytest
from netpilot.diagnostic_target import derive_diagnostic_target, merge_diagnostic_target, extract_target_subject, user_target
from netpilot.environment import EnvironmentProfile


@pytest.mark.parametrize("mode,provider,subject,relationship,limitation", [
    ("remote_browser","local","user_client","remote","remote_client_not_directly_observable"),
    ("mock","mock","mock_client","simulated","none"),
    ("server_local","local","user_client","unknown","unknown_target"),
    ("unknown","local","unknown","unknown","unknown_target"),
    ("mock","local","mock_client","simulated","provider_target_mismatch"),
])
def test_safe_derivation(mode,provider,subject,relationship,limitation):
    target = derive_diagnostic_target(EnvironmentProfile(client_mode=mode),provider)
    assert (target.subject,target.relationship_to_netpilot,target.limitation_code) == (subject,relationship,limitation)
    assert target.execution_context == ("netpilot_host" if provider == "local" else "mock_provider")


def test_trusted_same_host_only_and_user_override_has_priority():
    environment = EnvironmentProfile(client_mode="server_local")
    trusted = derive_diagnostic_target(environment,"local",same_host_confirmed=True)
    assert trusted.relationship_to_netpilot == "same_host" and trusted.limitation_code == "none"
    environment = EnvironmentProfile(client_mode="remote_browser")
    default = derive_diagnostic_target(environment,"local")
    host = merge_diagnostic_target(default,user_target("netpilot_host",environment,"local"),"local")
    assert host.source == "user" and host.confidence == "high" and host.target_version == 2
    assert merge_diagnostic_target(host,default,"local") == host
    assert merge_diagnostic_target(host,user_target("netpilot_host",environment,"local"),"local") == host


@pytest.mark.parametrize("message,expected", [
    ("检查这台 NetPilot 服务器能不能访问 GitHub","netpilot_host"),
    ("检查运行 NetPilot 的这台服务器是否能访问 GitHub","netpilot_host"),
    ("我的电脑上不了网","user_client"),
    ("如果我检查 NetPilot 服务器会怎样",None),
    ("不要检查 NetPilot 服务器",None),
    ("帮我检查网络",None),
])
def test_explicit_target_extraction_no_extra_classifier(message,expected):
    assert extract_target_subject(message) == expected


@pytest.mark.parametrize("source", ["user","mock","environment","system","inferred"])
def test_target_source_precedence(source):
    from netpilot.diagnostic_target import DiagnosticTarget, TARGET_PRECEDENCE
    original = DiagnosticTarget(subject="netpilot_host",relationship_to_netpilot="same_host",source=source)
    for challenger in TARGET_PRECEDENCE:
        candidate = DiagnosticTarget(subject="user_client",relationship_to_netpilot="remote",source=challenger)
        merged = merge_diagnostic_target(original,candidate,"local")
        assert merged.subject == ("user_client" if TARGET_PRECEDENCE[challenger] >= TARGET_PRECEDENCE[source] else "netpilot_host")
