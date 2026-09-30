from __future__ import annotations

from uuid import uuid4

from netpilot.agent import (
    AgentResult,
    AgentStatus,
    AgentToolStep,
    ResponseMode,
    SessionStore,
    TurnIntent,
)
from netpilot.tools.schemas import DNSLookupData, ToolResult


def _dns_result() -> AgentResult:
    return AgentResult(
        answer="DNS 解析异常。",
        status=AgentStatus.COMPLETED,
        tool_rounds=1,
        turn_intent=TurnIntent.DIAGNOSE,
        response_mode=ResponseMode.DIAGNOSTIC,
        steps=[
            AgentToolStep(
                round=1,
                tool_call_id="dns-1",
                tool_name="dns_lookup",
                arguments={"domain": "github.com"},
                tool_signature='dns_lookup:{"domain":"github.com"}',
                result=ToolResult[DNSLookupData](
                    success=True,
                    tool="dns_lookup",
                    summary="域名解析失败",
                    data=DNSLookupData(resolved=False, addresses=[]),
                    duration_ms=2,
                ),
            )
        ],
    )


def test_session_task_state_persists_structured_evidence_separately() -> None:
    owner = uuid4()
    store = SessionStore()
    session = store.create(owner)

    store.begin_turn(session.session_id, owner)
    store.finish_turn(
        session.session_id,
        "github.com 打不开",
        "DNS 解析异常。",
        result=_dns_result(),
    )

    state = store.task_state(session.session_id, owner)
    snapshot = store.get(session.session_id, owner)
    assert snapshot.message_count == 2
    assert snapshot.evidence_count == 1
    assert snapshot.turn_index == 1
    assert state.evidence[0].tool_name == "dns_lookup"
    assert state.evidence[0].status == "abnormal"
    assert state.evidence[0].data == {"resolved": False, "addresses": []}
    assert state.evidence[0].turn_index == 1
    assert state.evidence[0].tool_signature in state.executed_tool_signatures
    assert state.coverage.dns_checked is True
    assert state.last_evidence_sufficiency is not None
    assert state.last_evidence_sufficiency.sufficient is True
    assert state.hypotheses[0].name == "dns_resolution_path_failure"
    assert state.hypotheses[0].status == "supported"

    state.evidence.clear()
    assert store.get(session.session_id, owner).evidence_count == 1


def test_new_task_version_supersedes_old_evidence_without_deleting_it() -> None:
    owner = uuid4()
    store = SessionStore()
    session = store.create(owner)
    store.begin_turn(session.session_id, owner)
    store.finish_turn(session.session_id, "问题", "回答", result=_dns_result())

    assert store.advance_task_version(session.session_id, owner) == 2
    state = store.task_state(session.session_id, owner)

    assert len(state.evidence) == 1
    assert state.evidence[0].superseded is True
    assert state.reusable_evidence() == []
    assert state.executed_tool_signatures == set()
    assert state.coverage.checked_names() == []
    assert state.hypotheses == []
    assert state.last_evidence_sufficiency is None
