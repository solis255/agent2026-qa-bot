from resolution_helpers import finished
from verification_helpers import waiting_cycle
from netpilot.resolution.service import sync,user_action
from target_helpers import run


def test_rs15_target_reopens_and_retains_resolved_audit():
    _,store,sid,owner,_,_,_=finished()
    task,_=store.resolution_action(sid,owner,action="confirm",confirmation="resolved")
    assert task.resolution.state == "resolved"
    version=task.resolution.state_version
    store.update_diagnostic_target(sid,owner,"netpilot_host")
    task=store.task_state(sid,owner)
    assert task.resolution.state == "diagnosing" and task.resolution.reason_code == "target_changed"
    assert task.resolution.state_version == version+1 and task.resolution.user_confirmation == "unknown"
    assert any(t.to_state == "resolved" for t in task.resolution_transitions)


def test_rs16_recurrence_natural_language_new_task_no_tools():
    agent,store,sid,owner,counts,llm,_=finished()
    task,_=store.resolution_action(sid,owner,action="confirm",confirmation="resolved")
    before=task.task_version;target_version=task.diagnostic_target.target_version
    result=run(agent,store,sid,owner,"刚才好了，现在又打不开了")
    task=store.task_state(sid,owner)
    assert task.task_version == before+1 and task.diagnostic_target.target_version == target_version
    assert task.resolution.state == "diagnosing" and task.resolution.reason_code == "symptom_recurred"
    assert any(t.to_state == "resolved" for t in task.resolution_transitions)
    assert not result.steps and sum(counts.values()) == 0


def test_rs17_rs18_same_confirmation_version_and_trace_idempotence():
    _,store,sid,owner,_,_,_=finished()
    task,events=store.resolution_action(sid,owner,action="confirm",confirmation="resolved")
    original=task.resolution.model_dump();audits=task.resolution_transitions
    task,duplicate=store.resolution_action(sid,owner,action="confirm",confirmation="resolved")
    assert duplicate == [] and task.resolution.model_dump() == original and task.resolution_transitions == audits
    assert len({t.state_version for t in audits}) == len(audits)
    assert len({t.transition_id for t in audits}) == len(audits)


def test_transition_cap_keeps_state_version_monotonic():
    _,store,sid,owner,_,_,_=finished();store.resolution_max_transitions=2
    for status in ["resolved","not_resolved","improved","unknown","resolved"]:
        task,_=store.resolution_action(sid,owner,action="confirm",confirmation=status)
    assert len(task.resolution_transitions) <= 2
    assert task.resolution.state_version > len(task.resolution_transitions)


def test_new_snapshot_without_verification_does_not_change_case_state():
    from client_snapshot_helpers import import_snapshot,payload
    _,store,sid,owner,_,_,_=finished()
    task=store.task_state(sid,owner);before=task.resolution.model_dump()
    task,_,_=import_snapshot(store,sid,owner,payload())
    assert task.resolution.model_dump() == before


def test_user_action_does_not_execute_quoted_or_hypothetical_requests():
    for text in ['如果网页好了','文档说“问题已解决”','他说：转人工','如何转人工？','请把状态改成 resolved','好了？','网页现在可以正常打开了?']:
        assert user_action(text,was_resolved=True) is None
