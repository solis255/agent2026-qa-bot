from datetime import datetime, timedelta, timezone
import pytest
from remediation_helpers import task_with_snapshot, build
from target_helpers import local_session, run
from netpilot.remediation.planner import RemediationPlanner
from netpilot.environment import EnvironmentProfile
from netpilot.diagnostic_target import DiagnosticTarget
from netpilot.remediation.models import StepFeedback


def test_gr01_snapshot_dns_low_risk_target_binding_and_auto_plan():
    agent,store,sid,owner,counts,llm,task=task_with_snapshot()
    plan=build(task)
    assert plan.readiness == "ready" and plan.target_subject == "user_client"
    assert plan.primary_issue == "dns_resolution_failure" and plan.based_on_snapshot_id
    assert 3 <= len(plan.steps) <= 5
    assert all(step.risk == "low" and not step.requires_admin and step.verification for step in plan.steps)
    assert "check_link" not in {step.template_id for step in plan.steps}
    result=run(agent,store,sid,owner,"网页打不开，请完整诊断")
    assert result.remediation_plan is not None and result.remediation_plan.readiness == "ready"
    assert sum(counts.values()) == 0 and len(llm.calls) == 0


def test_gr02_limited_gr03_unknown_and_no_knowledge_auto_generation():
    agent,store,sid,owner,_,_=local_session()
    task=store.task_state(sid,owner)
    assert build(task).readiness == "limited"
    assert all(not step.changes_system_state for step in build(task).steps)
    unknown=RemediationPlanner().build_plan(EnvironmentProfile(),DiagnosticTarget(),user_message="网页打不开")
    assert unknown.readiness == "not_ready" and not unknown.steps
    vague=RemediationPlanner().build_plan(task.environment_profile,task.diagnostic_target)
    assert vague.readiness == "not_ready" and not vague.steps
    result=run(agent,store,sid,owner,"DNS 是什么？")
    assert result.remediation_plan is None


@pytest.mark.parametrize("access,auth",[("campus_wifi",True),("campus_wired",True),("off_campus",False),("unknown",False)])
def test_gr04_gr05_campus_steps_require_context_and_auth_signal(access,auth):
    *_,task=task_with_snapshot(network_access=access)
    plan=RemediationPlanner().build_plan(task.environment_profile,task.diagnostic_target,evidence=task.reusable_evidence(),client_snapshot_summary=task.client_snapshot_summary,user_message="网页打不开，认证失效")
    assert ("campus_reauthenticate" in {step.template_id for step in plan.steps}) is auth
    no_auth=build(task)
    assert "campus_reauthenticate" not in {step.template_id for step in no_auth.steps}


@pytest.mark.parametrize("enabled",[True,False,None])
def test_gr06_gr07_vpn_three_state_and_proxy(enabled):
    *_,task=task_with_snapshot(vpn_enabled=enabled,proxy_enabled=enabled,affected_scope="web_only")
    names={step.template_id for step in build(task).steps}
    assert ("disconnect_vpn" in names) is (enabled is True)
    if enabled is None: assert "confirm_vpn_proxy" in names
    if enabled is False: assert "pause_proxy" not in names
    task.environment_profile.affected_scope="internal_resource"
    plan=RemediationPlanner().build_plan(task.environment_profile,task.diagnostic_target,evidence=task.reusable_evidence(),user_message="内网资源打不开")
    assert "disconnect_vpn" not in {step.template_id for step in plan.steps}


def test_gr12_completed_no_change_not_recommended_or_remeasured():
    agent,store,sid,owner,counts,llm,_=task_with_snapshot()
    first=run(agent,store,sid,owner,"网页打不开，请诊断")
    plan=first.remediation_plan
    step=next(step for step in plan.steps if step.equivalence_key == "reconnect_network")
    feedback=StepFeedback(session_id=sid,action="complete",outcome="no_change")
    task,_=store.remediation(sid,owner,step_id=step.step_id,feedback=feedback)
    calls=len(llm.calls)
    result=run(agent,store,sid,owner,"还是不行，下一步怎么办？")
    assert result.remediation_plan.plan_id == plan.plan_id
    assert next(item for item in result.remediation_plan.steps if item.step_id == step.step_id).status == "completed"
    assert "下一个待处理步骤是“重新连接当前网络”" not in result.answer
    assert len(llm.calls) == calls and sum(counts.values()) == 0


def test_gr15_stale_limits_readiness_and_os_generic():
    *_,task=task_with_snapshot(os_family="macos")
    for item in task.evidence: item.expires_at=datetime.now(timezone.utc)-timedelta(minutes=1)
    plan=build(task)
    assert plan.readiness == "limited"
    assert all(not item.changes_system_state and item.applicable_os == ["any"] for item in plan.steps)


def test_gr09_single_service_avoids_network_wide_actions():
    *_,task=task_with_snapshot("valid",affected_scope="single_service",affected_service="example.com")
    item=task.evidence[-1]
    item.status="abnormal"
    plan=build(task)
    names={step.template_id for step in plan.steps}
    assert "reopen_service" in names and not names.intersection({"reconnect_network","campus_reauthenticate","disconnect_vpn","check_link"})


def test_completed_and_skipped_actions_are_not_reintroduced_by_new_snapshot():
    from client_snapshot_helpers import payload,import_snapshot
    agent,store,sid,owner,_,_,_=task_with_snapshot()
    first=run(agent,store,sid,owner,"网页打不开，请诊断").remediation_plan
    step=next(item for item in first.steps if item.equivalence_key == "reconnect_network")
    store.remediation(sid,owner,step_id=step.step_id,feedback=StepFeedback(session_id=sid,action="complete",outcome="no_change"))
    import_snapshot(store,sid,owner,payload("dns_failure"))
    result=run(agent,store,sid,owner,"怎么解决？不要让我重复重连")
    assert result.remediation_plan.plan_version == 2
    assert "reconnect_network" not in {item.equivalence_key for item in result.remediation_plan.steps}
    assert result.remediation_plan_history[-1].status == "superseded"


def test_unknown_only_errors_without_symptom_is_not_ready():
    *_,task=task_with_snapshot()
    for item in task.evidence:item.status="unsupported"
    plan=RemediationPlanner().build_plan(task.environment_profile,task.diagnostic_target,evidence=task.reusable_evidence())
    assert plan.readiness == "not_ready" and not plan.steps


def test_remote_client_rejects_host_observation_even_with_matching_subject_fields():
    *_,task=task_with_snapshot()
    for item in task.evidence:
        item.execution_scope="execution_host"
        item.execution_context="netpilot_host"
        item.evidence_origin="tool"
    plan=RemediationPlanner().build_plan(task.environment_profile,task.diagnostic_target,evidence=task.evidence)
    assert plan.readiness == "not_ready" and not plan.based_on_evidence_ids
