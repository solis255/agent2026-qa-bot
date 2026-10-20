"""Expected states are assertions/documentation, never assignments to task state."""
from types import MappingProxyType
from .models import DemoScenario, DemoScenarioStep
from netpilot.environment import EnvironmentUpdate


def scenario(key, title, fixtures, *, vpn=False, scope="web_only", issue="dns_resolution_failure",
             templates=("reopen_browser", "campus_reconnect"), result=None, resolution=None, escalation=False):
    actions = [
        ("system", "创建独立的远程 Windows 客户端演示会话", {"subject": "user_client", "relationship": "remote"}),
        ("user", "描述现象并确认环境；主机网络工具应被阻止", {"host_handler_calls": 0}),
        ("fixture", "加载修复前快照，通过正式校验和 ingestion", {"primary_issue": issue}),
        ("user", "分析已有证据并生成批准目录中的低风险手动计划", {"risk": "low"}),
    ]
    if result:
        actions += [("user", "模拟完成手动步骤；使用正式反馈 API", {}),
                    ("fixture", "加载下一份 After 快照；由正式 Verifier 计算差异", {"verification": result})]
    if resolution == "resolved": actions.append(("user", "明确确认网页恢复", {"resolution": "resolved"}))
    if escalation: actions.append(("user", "完成剩余低风险步骤和第二轮 After，再生成报修材料", {"resolution": "escalated", "completeness": "complete"}))
    if key == "recurrence": actions.append(("user", "刚才好了，现在又打不开了", {"resolution": "diagnosing", "reason": "symptom_recurred"}))
    return DemoScenario(scenario_id=key, title=title, description="DEMO / 模拟数据：使用受控客户端快照，无真实网络故障注入。",
        environment_fixture=EnvironmentUpdate(os_family="windows", os_version="10.0.26100", network_access="campus_wifi",
            vpn_enabled=vpn, proxy_enabled=False, affected_scope=scope, affected_service="示例服务" if scope == "single_service" else None),
        snapshot_fixtures=tuple(fixtures), expected_initial_issue=issue, expected_remediation_templates=templates,
        expected_verification_result=result, expected_resolution_state=resolution, supports_escalation=escalation,
        recommended_input="只有示例服务打不开，其他网页和应用正常，请分析。" if scope == "single_service" else "普通网页打不开，但是我现在开着 VPN，请分析。" if vpn else "我的微信能用，但网页打不开，帮我检查一下。",
        steps=tuple(DemoScenarioStep(order=i, actor=actor, action=action, expected_state=state) for i, (actor, action, state) in enumerate(actions, 1)))


SCENARIOS = MappingProxyType({item.scenario_id: item for item in [
    scenario("dns_recovery", "A · DNS 修复成功", ["dns_recovery_before", "dns_recovery_after"], result="improved", resolution="resolved"),
    scenario("dns_escalation", "B · DNS 多轮无改善", ["dns_escalation_before", "dns_escalation_after_1", "dns_escalation_after_2"], result="unchanged", resolution="escalated", escalation=True),
    scenario("vpn_proxy", "C · VPN 场景", ["vpn_enabled"], vpn=True, templates=("disconnect_vpn",)),
    scenario("vpn_unknown", "C 变体 · VPN 状态未知", ["vpn_enabled"], vpn=None, templates=("confirm_vpn_proxy",)),
    scenario("single_service", "D · 单服务故障", ["single_service"], scope="single_service", issue="single_service", templates=("check_service_status", "reopen_service")),
    scenario("recurrence", "E · 问题复发", ["dns_recovery_before", "dns_recovery_after"], result="improved", resolution="resolved"),
]})
