from resolution_helpers import finished
from netpilot.resolution.service import context
from netpilot.agent.context_builder import build_task_context_message
from netpilot.agent.intent import TurnIntent
from target_helpers import run


def test_context_compact_authoritative_separates_confirmation():
    *_,task=finished()
    text=build_task_context_message(user_message="解释状态",intent=TurnIntent.ANALYZE_EXISTING,task_version=task.task_version,
        evidence=task.reusable_evidence(),diagnostic_target=task.diagnostic_target,resolution=task.resolution).content
    assert "RESOLUTION STATUS" in text and "State: improved" in text and "User confirmation: unknown" in text
    assert "not a submitted ticket" in text


def test_old_scope_context_never_claims_resolved():
    from netpilot.diagnostic_target import DiagnosticTarget
    *_,task=finished()
    task.resolution.state="resolved"
    text=context(task.resolution,DiagnosticTarget(subject="netpilot_host",target_version=99),task.task_version)
    assert "State: diagnosing" in text and "State: resolved" not in text


def test_rs23_trace_once_and_disabled_respects_setting():
    _,store,sid,owner,_,_,_=finished()
    task,events=store.resolution_action(sid,owner,action="confirm",confirmation="resolved")
    assert [e.title for e in events] == ["确认问题已解决"]
    assert events[0].event_origin == "resolution" and "关键异常指标已恢复" in events[0].summary
    assert "我想" not in events[0].summary
    store.reasoning_trace_enabled=False
    task,events=store.resolution_action(sid,owner,action="support")
    assert events == [] and task.resolution.state == "escalated"


def test_model_receives_current_resolution_not_a_state_write_tool():
    agent,store,sid,owner,counts,llm,_=finished()
    run(agent,store,sid,owner,"TCP 协议是什么？")
    assert any("RESOLUTION STATUS" in (m.content or "") for m in llm.calls[-1][0])
    assert not any("resolution" in s["function"]["name"] for s in agent.registry.schemas())
    assert sum(counts.values()) == 0
