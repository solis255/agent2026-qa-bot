from escalation_helpers import case
from netpilot.escalation.builder import build_package
from netpilot.escalation.handoff_catalog import handoff_checks


def test_ep14_safe_static_dns_checks():
    text="\n".join(handoff_checks(["client_snapshot.dns_check"]))
    assert all(s in text for s in ["DNS / DHCP","DNS 服务可用性","AP","VLAN"])
    assert all(s not in text for s in ["重启核心交换机","删除 ACL","关闭安全软件","修改生产 DNS"])


def test_ep15_mock_prominent_not_real_network():
    from netpilot.agent import SessionStore
    from uuid import uuid4
    store=SessionStore(provider_kind="mock",environment_client_mode="mock")
    owner=uuid4();sid=store.create(owner).session_id
    package=build_package(store.task_state(sid,owner))
    assert "Mock" in package.target.notice and "不代表真实校园网络" in package.target.notice
    assert any("不得据此处理真实" in c for c in package.recommended_handoff_checks)


def test_knowledge_sources_are_separate_self_contained_and_ranked():
    from netpilot.remediation.models import RemediationSource
    task=case()
    task.remediation_plan.sources=[RemediationSource(source_ref="COMM",source_type="community",title="社区 VPN",source="https://wiki.example/vpn?token=abc123&lang=zh"),
        RemediationSource(source_ref="OFF",source_type="official",title="官方说明",source="https://example.edu/help")]
    package=build_package(task)
    assert "[official]" in package.source_refs[0]
    assert "需官方核验" in package.source_refs[1] and "lang=zh" in package.source_refs[1]
    assert "abc123" not in package.model_dump_json()
    assert all("knowledge" not in e.category for e in package.evidence_summary)
