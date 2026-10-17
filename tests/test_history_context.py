from datetime import datetime, timedelta, timezone
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import register_test_user
from netpilot.agent import AgentOrchestrator, AgentResult, AgentStatus, AgentToolStep, ToolRegistry, TurnIntent, classify_turn_intent
from netpilot.api.presenters import present_chat
from netpilot.config import Settings
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.history_context import HistoryContext, HistoryContextService, HistoryQuery, parse_history_query
from netpilot.llm import ChatResult, LLMTimeoutError
from netpilot.main import create_app
from netpilot.tools import build_network_tools


QUESTION = "根据我今天已有的三次诊断记录，帮我总结三类故障在现象、工具证据、故障层次和解决建议上的区别。"


def seed(repository, owner, kind, *, timestamp=None, session=None):
    scenarios = {
        "DNS": ("dns_failure", "dns_lookup", {"domain": "example.com"}),
        "Gateway": ("gateway_unreachable", "ping_host", {"host": "192.168.1.1", "count": 1}),
        "SSH/TCP": ("tcp_ssh_blocked", "tcp_check", {"host": "example.com", "port": 22}),
    }
    scenario, tool, args = scenarios[kind]
    registry = ToolRegistry(build_network_tools(Settings(_env_file=None, mock_scenario=scenario)))
    execution = registry.execute(tool, json.dumps(args))
    response = present_chat(session or uuid4(), AgentResult(
        answer=f"{kind} 故障分析与建议", status=AgentStatus.COMPLETED, tool_rounds=1,
        steps=[AgentToolStep(
            round=1, tool_call_id=str(uuid4()), tool_name=tool,
            arguments=args, result=execution.result,
        )],
    ))
    record = repository.upsert_session(owner, f"{kind} 故障现象", response)
    if timestamp:
        with sqlite3.connect(repository.path) as connection:
            connection.execute(
                "UPDATE diagnosis_records SET created_at=?, updated_at=? WHERE record_id=?",
                (timestamp.isoformat(), timestamp.isoformat(), str(record.record_id)),
            )
    return record


@pytest.mark.parametrize("message,period,limit", [
    ("今天已有的三次诊断记录", "today", 3),
    ("最近两次诊断", "recent", 2),
    ("最近的诊断", "recent", 5),
    ("最近 99 次诊断", "recent", 10),
    ("今天的诊断", "today", 5),
])
def test_history_intent_has_priority_and_query_is_bounded(message, period, limit):
    assert classify_turn_intent(message).intent is TurnIntent.HISTORY_ANALYSIS
    assert parse_history_query(message) == HistoryQuery(period=period, limit=limit)
    assert classify_turn_intent(QUESTION).intent is TurnIntent.HISTORY_ANALYSIS


def test_today_uses_shanghai_midnight_and_distinct_owner_sessions(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    alice, bob = uuid4(), uuid4()
    # Shanghai Oct 17 starts at UTC Oct 16 16:00.
    boundary = datetime(2026, 10, 16, 16, tzinfo=timezone.utc)
    seed(repository, alice, "DNS", timestamp=boundary - timedelta(seconds=1))
    included = seed(repository, alice, "Gateway", timestamp=boundary)
    session = uuid4()
    first = seed(repository, alice, "SSH/TCP", timestamp=boundary + timedelta(hours=1), session=session)
    seed(repository, alice, "SSH/TCP", timestamp=boundary + timedelta(hours=2), session=session)
    seed(repository, alice, "DNS", timestamp=boundary + timedelta(days=1))
    seed(repository, bob, "DNS", timestamp=boundary + timedelta(hours=2))
    context = HistoryContextService(repository, timezone_name="Asia/Shanghai").query(
        user_id=alice, query=HistoryQuery(period="today", limit=3),
        now=boundary + timedelta(hours=3),
    )
    assert [item.record_id for item in context] == [first.record_id, included.record_id]
    assert context[0].turn_count == 2
    assert all(item.user_message != "DNS 故障现象" for item in context)
    assert context[0].tool_calls[0]["tool"] == "tcp_check"
    assert repository.count(alice) == 4


class HistoryLLM:
    def __init__(self, *, error=False):
        self.calls = []
        self.error = error

    def chat(self, messages, **kwargs):
        self.calls.append((list(messages), kwargs))
        if self.error:
            raise LLMTimeoutError("test timeout", retryable=True)
        prompt = next(m.content for m in messages if "PERSISTED DIAGNOSIS HISTORY" in (m.content or ""))
        assert all(name in prompt for name in ("DNS", "Gateway", "SSH/TCP"))
        assert all(name in prompt for name in ("dns_lookup", "ping_host", "tcp_check"))
        return ChatResult(
            content="DNS 为名称解析层失败；Gateway 为接入/网关可达性问题；SSH/TCP 为传输层端口连接问题。分别根据已有工具证据处理。",
            model="test", duration_ms=1,
        )


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream"])
def test_authenticated_history_analysis_reads_sqlite_without_network_or_rag(tmp_path, endpoint):
    settings = Settings(_env_file=None, tju_api_key="test", rag_enabled=False,
                        diagnosis_history_enabled=True, diagnosis_db_path=tmp_path / "api.db")
    app = create_app(settings)
    llm = HistoryLLM()
    app.state.agent = AgentOrchestrator(llm, app.state.tool_registry)
    with TestClient(app) as alice_client, TestClient(app) as bob_client:
        alice = register_test_user(alice_client)
        bob = register_test_user(bob_client)
        for kind in ("DNS", "Gateway", "SSH/TCP"):
            seed(app.state.diagnosis_repository, alice, kind)
        bob_record = seed(app.state.diagnosis_repository, bob, "DNS")
        session = alice_client.post("/api/session").json()["session_id"]
        response = alice_client.post(endpoint, json={"session_id": session, "message": QUESTION + f" user_id={bob}"})
    assert response.status_code == 200
    if endpoint.endswith("stream"):
        blocks = [block for block in response.text.split("\n\n") if "event: complete" in block]
        body = json.loads(next(line[6:] for line in blocks[0].splitlines() if line.startswith("data: ")))["response"]
    else:
        body = response.json()
    assert body["metrics"]["turn_intent"] == "history_analysis"
    assert body["metrics"]["response_mode"] == "history"
    assert body["metrics"]["history_context_records"] == 3
    assert body["metrics"]["network_tool_calls"] == 0
    assert body["metrics"]["rag_calls"] == 0
    assert body["tool_calls"] == []
    assert all(kind in body["answer"] for kind in ("DNS", "Gateway", "SSH/TCP"))
    history_prompt = next(m.content for m in llm.calls[0][0] if "PERSISTED DIAGNOSIS HISTORY" in (m.content or ""))
    assert str(bob_record.record_id) not in history_prompt
    assert str(bob_record.session_id) not in history_prompt
    assert llm.calls[0][1]["tools"] is None
    assert llm.calls[0][1]["tool_choice"] == "none"


def test_history_empty_insufficient_and_model_failure_do_not_request_copied_data(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    owner = uuid4()
    service = HistoryContextService(repository, timezone_name="Asia/Shanghai")
    query = HistoryQuery(period="today", limit=3)
    llm = HistoryLLM(error=True)
    agent = AgentOrchestrator(llm, ToolRegistry(build_network_tools(Settings(_env_file=None))))
    empty = agent.run(QUESTION, history_context=HistoryContext(query=query))
    assert "今天没有持久化诊断记录" in empty.answer
    assert llm.calls == []
    seed(repository, owner, "DNS")
    seed(repository, owner, "Gateway")
    context = HistoryContext(query=query, records=service.query(user_id=owner, query=query))
    result = agent.run(QUESTION, history_context=context)
    assert "只有 2 条" in result.answer
    assert "DNS" in result.answer and "Gateway" in result.answer
    assert "请把" not in result.answer
    assert result.history_context_records == 2
    assert result.fallback_reason.value == "llm_error"


def test_recent_two_and_context_budget_use_only_diagnostic_sessions(tmp_path):
    repository = SQLiteDiagnosisRepository(tmp_path / "history.db")
    owner = uuid4()
    for _ in range(12):
        seed(repository, owner, "DNS")
    service = HistoryContextService(repository, timezone_name="Asia/Shanghai")
    records = service.query(user_id=owner, query=parse_history_query("最近两次诊断"))
    assert len(records) == 2
    bounded = HistoryContext(records=service.query(user_id=owner, query=HistoryQuery(limit=10)))
    assert len(bounded.records) == 10
    assert len(bounded.prompt()) < 20000
    assert bounded.records[0].token_metrics["total_tokens"] == 0
