from datetime import timedelta
from uuid import uuid4
import pytest
from escalation_helpers import case
from target_helpers import local_session,run
from netpilot.escalation.builder import build_package,material_request
from netpilot.escalation.service import ensure_package,context


def test_ep01_ep05_ep06_complete_escalation_and_real_step_statuses():
    task=case()
    steps=task.remediation_plan.steps
    steps[0]=steps[0].model_copy(update={"status":"completed","outcome":"no_change"})
    if len(steps)>1:steps[1]=steps[1].model_copy(update={"status":"skipped","outcome":"unknown"})
    if len(steps)>2:steps[2]=steps[2].model_copy(update={"status":"failed","outcome":"unknown"})
    p=build_package(task)
    assert p.completeness == "complete"
    assert p.resolution.state == "escalated" and p.escalation_reason.reason_code == "repeated_no_improvement"
    assert len(p.verification_summary)==2 and all(c.result == "unchanged" for c in p.verification_summary)
    assert p.remediation_summary[0].status == "completed" and p.remediation_summary[0].outcome == "no_change"
    assert {s.status for s in p.remediation_summary} == {s.status for s in steps}
    assert all(s.started_at is None for s in p.remediation_summary)
    assert all("用户" in e.origin for e in p.evidence_summary)


def test_ep03_ep04_evidence_limit_and_dedup():
    task=case();base=task.evidence[-1]
    task.evidence=[base.model_copy(deep=True,update={"evidence_id":str(uuid4()),"data":{**base.data,"target":f"host{i}.example"}}) for i in range(30)]
    assert len(build_package(task).evidence_summary)==12
    task.evidence=[base.model_copy(deep=True,update={"evidence_id":str(uuid4())}) for _ in range(5)]
    assert len(build_package(task).evidence_summary)==1


def test_stale_and_wrong_target_never_current_fact():
    task=case()
    for e in task.evidence:e.expires_at=e.observed_at-timedelta(minutes=1)
    task.evidence.append(task.evidence[-1].model_copy(update={"target_subject":"netpilot_host","evidence_origin":"tool","execution_scope":"execution_host","execution_context":"netpilot_host","summary":"FOREIGN-HOST"}))
    p=build_package(task)
    assert p.completeness=="limited" and all(e.stale and e.summary.startswith("历史") for e in p.evidence_summary)
    assert "FOREIGN-HOST" not in p.model_dump_json()
    assert all(c.historical for c in p.verification_summary)


def test_ep12_missing_after_partial():
    task=case();task.verification_cycles=[]
    p=build_package(task)
    assert p.completeness=="partial" and any("After" in n for n in p.completeness_notes)


def test_ep13_no_direct_evidence_limited():
    agent,store,sid,owner,_,_=local_session()
    p=build_package(store.task_state(sid,owner))
    assert p.completeness=="limited" and not p.evidence_summary


def test_ep16_ep17_versions_idempotence_fingerprint_and_trace():
    task=case();old_resolution=task.resolution.model_dump_json()
    first,events=ensure_package(task)
    assert [e.title for e in events]==["生成升级报修材料"]
    old=first.model_dump_json()
    again,events=ensure_package(task)
    assert again==first and not events and len(task.escalation_packages)==1
    task.resolution.reason_summary="人工支持建议补充信息"  # may change without state_version
    second,_=ensure_package(task)
    assert second.package_version==2 and first.model_dump_json()==old and second.package_digest!=first.package_digest
    for i in range(7):
        task.remediation_symptom=f"网页仍无法访问（补充{i}）";ensure_package(task)
    assert len(task.escalation_packages)==5 and task.escalation_package_sequence==9
    assert "ESCALATION PACKAGE STATUS" in context(task.escalation_packages)
    assert "evidence_summary" not in context(task.escalation_packages)


@pytest.mark.parametrize("message",["帮我整理给运维人员","我要报修","帮我生成报修材料","生成升级报修材料包"])
def test_ep02_explicit_chat_request_no_llm_tool_or_state_change(message):
    agent,store,sid,owner,counts,llm=local_session()
    before=store.task_state(sid,owner).resolution.model_dump()
    result=run(agent,store,sid,owner,message)
    task=store.task_state(sid,owner)
    assert task.resolution.model_dump()==before and result.escalation_requested
    assert len(task.escalation_packages)==1 and not llm.calls and sum(counts.values())==0
    assert "已生成报修材料" in result.answer
    assert {e.title for e in result.reasoning_trace} >= {"生成升级报修材料","报修材料信息不完整"}


@pytest.mark.parametrize("message",["报修需要什么材料？","不要帮我生成报修材料","他说我要报修","如果我要报修怎么办","生成诊断报告"])
def test_material_request_is_explicit(message):
    assert not material_request(message)


def test_target_switch_does_not_copy_other_subject_issue_or_plan():
    task=case();task.diagnostic_target=task.diagnostic_target.model_copy(update={"subject":"netpilot_host","target_version":2})
    task.resolution=task.resolution.model_copy(update={"state":"diagnosing","reason_code":"target_changed"})
    p=build_package(task)
    assert not p.evidence_summary and not p.remediation_summary and not p.verification_summary
    assert p.issue.primary_issue=="undetermined" and "当前对象明确症状" in p.issue.current_symptom
    assert task.remediation_symptom not in p.model_dump_json()


def test_context_contains_only_status_not_artifact_body():
    from netpilot.agent.context_builder import build_task_context_message
    from netpilot.agent.intent import TurnIntent
    task=case();p,_=ensure_package(task)
    message=build_task_context_message(user_message="请分析已有证据",intent=TurnIntent.ANALYZE_EXISTING,task_version=task.task_version,escalation_packages=[p])
    assert "ESCALATION PACKAGE STATUS" in message.content and "completeness: complete" in message.content
    assert "package_digest" not in message.content and "recommended_handoff_checks" not in message.content


def test_new_pending_verification_cannot_borrow_older_after_for_completeness():
    task=case();latest=task.verification_cycles[-1]
    task.verification_cycles.append(latest.model_copy(deep=True,update={"verification_id":uuid4(),"status":"awaiting_after_evidence","after":None,"completed_at":None,"result":"unknown"}))
    p=build_package(task)
    assert p.completeness=="partial" and any("After" in n for n in p.completeness_notes)
