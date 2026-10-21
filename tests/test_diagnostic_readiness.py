"""13B rule matrix and evidence eligibility boundaries, using formal ingestion."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from client_snapshot_helpers import import_snapshot
from target_helpers import local_session
from netpilot.agent.intent import classify_turn_intent
from netpilot.agent.coverage import coverage_from_observations
from netpilot.conversation_context.models import ContextAcquisitionState, DiagnosticReadiness
from netpilot.conversation_context.acquisition import acquire_context
from netpilot.conversation_context.readiness import assess_diagnostic_readiness, client_evidence_support
from netpilot.client_snapshot.service import usable_client_snapshot_evidence
from netpilot.diagnostic_target import derive_diagnostic_target
from netpilot.environment import EnvironmentProfile


def assess(message="微信正常，但所有网页打不开", *, os="windows", scope="web_only", kind="local", task=None, question=None, acquisition=None):
    env = task.environment_profile if task else EnvironmentProfile(os_family=os, affected_scope=scope, client_mode="remote_browser")
    if task:
        env = env.model_copy(update={"affected_scope":scope})
    return assess_diagnostic_readiness(classification=classify_turn_intent(message, has_evidence=bool(task and task.evidence)),
        message=message, environment=env, context_question=question,
        target=task.diagnostic_target if task else derive_diagnostic_target(env, kind), provider_kind=kind,
        reusable_evidence=task.reusable_evidence() if task else (), task_version=task.task_version if task else 1,
        acquisition_state=acquisition)


@pytest.mark.parametrize("message,os,scope,expected,action", [
    ("eduroam 是什么？","unknown","unknown","knowledge_only","answer_knowledge"),
    ("天津大学 VPN 怎么使用？","windows","all_network","knowledge_only","answer_knowledge"),
    ("IPv6 是什么？","unknown","unknown","knowledge_only","answer_knowledge"),
    ("微信正常，但所有网页打不开","windows","web_only","need_client_evidence","request_client_evidence"),
    ("所有应用都不能联网，请检查网络","windows","all_network","need_client_evidence","request_client_evidence"),
    ("帮我检查一下我的 DNS","windows","single_service","need_client_evidence","request_client_evidence"),
    ("检测一下我的网络","windows","unknown","need_client_evidence","request_client_evidence"),
    ("看看我的默认网关","windows","unknown","need_client_evidence","request_client_evidence"),
    ("微信正常，但网页打不开","unknown","web_only","need_context","ask_context"),
    ("微信正常，但网页打不开","macos","web_only","need_client_evidence","continue_with_limitations"),
    ("微信正常，但网页打不开","linux","web_only","need_client_evidence","continue_with_limitations"),
    ("只有 GitHub 打不开，百度正常","windows","single_service","ready","continue_with_limitations"),
    ("列表里完全找不到校园 WiFi","windows","all_network","ready","continue_with_limitations"),
])
def test_p0_matrix(message, os, scope, expected, action):
    result = assess(message, os=os, scope=scope)
    assert (result.state, result.recommended_action) == (expected, action)
    assert not result.can_use_host_network_tools and not result.can_use_mock_tools


@pytest.mark.parametrize("message", ["VPN 怎么安装？", "网页打不开"])
def test_existing_context_question_is_authoritative(message):
    env = EnvironmentProfile()
    acquired = acquire_context(message, env, ContextAcquisitionState())
    result = assess(message, question=acquired.question)
    assert result.state == "need_context" and result.missing_context_fields == [acquired.question.field]


@pytest.mark.parametrize("os,supported", [("windows",True),("macos",False),("linux",False),("android",False),("ios",False),("unknown",None)])
def test_platform_support(os, supported):
    assert client_evidence_support(EnvironmentProfile(os_family=os)) is supported


def test_fresh_sufficient_snapshot_prefers_existing():
    _, store, sid, owner, *_ = local_session()
    task, *_ = import_snapshot(store, sid, owner)
    result = assess(task=task)
    assert result.has_usable_client_evidence and result.recommended_action == "analyze_existing"
    assert result.state == "ready"


@pytest.mark.parametrize("mutation", ["stale", "skew", "superseded", "not_reusable", "old_task", "old_target", "other_subject", "expired", "no_expiry"])
def test_invalid_snapshot_is_retained_but_does_not_satisfy_readiness(mutation):
    _, store, sid, owner, *_ = local_session()
    task, *_ = import_snapshot(store, sid, owner)
    for record in task.evidence:
        if mutation == "stale": record.stale = True
        if mutation == "skew": record.clock_skew_suspected = True
        if mutation == "superseded": record.superseded = True
        if mutation == "not_reusable": record.reusable = False
        if mutation == "old_task": record.task_version += 1
        if mutation == "old_target": record.target_version += 1
        if mutation == "other_subject": record.target_subject = "netpilot_host"
        if mutation == "expired": record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        if mutation == "no_expiry": record.expires_at = None
    assert not usable_client_snapshot_evidence(task)
    result = assess(task=task)
    assert not result.has_usable_client_evidence and result.state == "need_client_evidence"
    assert len(task.evidence) == 5


def test_collector_cannot_fill_ip_connectivity_gap_does_not_request_upload_again():
    _, store, sid, owner, *_ = local_session()
    task, *_ = import_snapshot(store, sid, owner)
    result = assess("所有网页打不开，请完整排查", task=task)
    assert result.state == "ready" and result.recommended_action == "continue_with_limitations"
    assert "ip_connectivity" in result.evidence_gap


def test_usable_but_missing_collectable_dns_requests_new_evidence():
    _, store, sid, owner, *_ = local_session()
    task, *_ = import_snapshot(store, sid, owner)
    task.evidence = [r for r in task.evidence if not r.tool_name.endswith("dns_check")]
    result = assess("帮我检查我的 DNS", task=task)
    assert result.has_usable_client_evidence and result.state == "need_client_evidence"
    assert result.evidence_gap == ["dns"]


def test_unknown_answer_does_not_loop_and_environment_is_not_evidence():
    state = ContextAcquisitionState(asked_fields=["os_family"], unknown_fields=["os_family"])
    result = assess(os="unknown", acquisition=state)
    assert result.recommended_action == "continue_with_limitations"
    assert not any(coverage_from_observations().model_dump().values())


def test_strict_model_and_legacy_task_default():
    from netpilot.agent.task_state import SessionTaskState
    assert SessionTaskState(session_id=uuid4(),owner_user_id=uuid4()).last_diagnostic_readiness is None
    with pytest.raises(ValidationError):
        DiagnosticReadiness(**assess().model_dump(), raw_message="secret")
    assert "message" not in DiagnosticReadiness.model_fields


def test_mock_uses_existing_mock_capability():
    result=assess("检查 DNS",kind="mock")
    assert result.state == "ready" and result.recommended_action == "run_allowed_diagnostics"
    assert result.can_use_mock_tools and not result.can_use_host_network_tools
