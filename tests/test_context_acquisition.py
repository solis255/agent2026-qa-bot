import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import register_test_user
from netpilot.agent import AgentOrchestrator, SessionStore, ToolRegistry
from netpilot.config import Settings
from netpilot.demo.runtime import FixtureOnlyTools
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.main import create_app
from test_tool_policy import DirectLLM


@pytest.fixture
def context_app(tmp_path):
    app = create_app(Settings(_env_file=None, tju_api_key="context-test-only", tool_mode="local", rag_enabled=False,
        diagnosis_db_path=tmp_path / "context.db", diagnosis_history_enabled=True))
    tools, llm = FixtureOnlyTools(), DirectLLM("当前是知识或上下文回答，未进行客户端网络检测。")
    app.state.agent = AgentOrchestrator(llm, ToolRegistry(tools), reasoning_summary_llm_enabled=True)
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        yield app, client, owner, sid, tools, llm


def send(client, sid, message, **values):
    response = client.post("/api/chat", json={"session_id":sid, "message":message, **values})
    assert response.status_code == 200, response.text
    return response.json()


def complete_sse(response):
    assert response.status_code == 200, response.text
    for block in response.text.split("\n\n"):
        if "event: complete" in block:
            return json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))["response"]
    pytest.fail("no complete event")


def test_tc02_no_tools_llm_or_fabricated_diagnosis(context_app):
    app, client, owner, sid, tools, llm = context_app
    result = send(client, sid, "网络有问题")
    assert result["ui_action"]["field"] == "affected_scope"
    assert result["diagnosis"]["primary_issue"] in {"undetermined","insufficient_evidence"}
    assert result["metrics"]["network_tool_calls"] == 0 and not result["client_evidence"]
    assert not llm.calls and tools.handler_calls == 0
    task = app.state.sessions.task_state(UUID(sid), owner)
    assert task.context_acquisition.asked_fields == ["affected_scope"] and not task.evidence


def test_tc07_chip_merge_normal_transcript_and_persistence(context_app):
    app, client, owner, sid, tools, llm = context_app
    # 13B may additionally ask OS before collection; this test isolates the
    # original scope/access journey with the browser's known platform.
    assert client.patch("/api/session/environment/browser",json={"session_id":sid,"os_family":"windows"}).status_code == 200
    send(client, sid, "校园网连不上")
    scope = send(client, sid, "其他应用也不能联网", context_answer={"field":"affected_scope","value":"all_network"})
    assert scope["ui_action"]["field"] == "network_access"
    result = send(client, sid, "ignored untrusted text", context_answer={"field":"network_access","value":"campus_wifi"})
    assert result["environment_profile"]["network_access"] == "campus_wifi"
    assert result["environment_profile"]["field_sources"]["network_access"] == {"source":"user","confidence":"high"}
    assert result["redacted_user_message"] == "校园 WiFi" and result["ui_action"]["type"] == "client_check"
    task = app.state.sessions.task_state(UUID(sid), owner)
    assert task.turn_index == 3 and not task.evidence and tools.handler_calls == 0
    assert task.original_symptom == task.remediation_symptom == "校园网连不上"
    record = SQLiteDiagnosisRepository(app.state.settings.diagnosis_db_path).get(owner, UUID(result["record_id"]))
    assert record.context_acquisition == task.context_acquisition
    assert [t.user_message for t in record.conversation_turns] == ["校园网连不上","其他应用也不能联网","校园 WiFi"]
    assert not record.context_acquisition.last_question_field


@pytest.mark.parametrize("answer,status", [({"field":"api_key","value":"secret-value"},422), ({"field":"network_access","value":"../../etc/passwd"},422), ({"field":"network_access","value":"campus_wifi"},409)])
def test_tc08_rejected_answer_does_not_change_session_or_echo(context_app, answer, status):
    app, client, owner, sid, *_ = context_app
    before = app.state.sessions.task_state(UUID(sid), owner)
    response = client.post("/api/chat", json={"session_id":sid,"message":"answer","context_answer":answer})
    assert response.status_code == status
    assert "secret-value" not in response.text and "../../etc/passwd" not in response.text
    assert app.state.sessions.task_state(UUID(sid), owner) == before
    assert not app.state.sessions.get(UUID(sid), owner).busy


def test_tc11_chat_and_sse_have_same_question_and_environment(context_app):
    _, client, _, sid, *_ = context_app
    other = client.post("/api/session").json()["session_id"]
    plain = send(client, sid, "网页打不开。")
    streamed = complete_sse(client.post("/api/chat/stream", json={"session_id":other,"message":"网页打不开。"}))
    assert plain["answer"] == streamed["answer"] and plain["ui_action"] == streamed["ui_action"]
    assert {k:v for k,v in plain["environment_profile"].items() if k != "updated_at"} == {k:v for k,v in streamed["environment_profile"].items() if k != "updated_at"}
    reply = complete_sse(client.post("/api/chat/stream", json={"session_id":other,"message":"不清楚","context_answer":{"field":"affected_scope","value":"unknown"}}))
    assert reply["context_acquisition"]["unknown_fields"] == ["affected_scope"]
    assert reply["ui_action"] is None


def test_tc03_full_user_facts_and_tc13_advanced_form(context_app):
    _, client, _, sid, *_ = context_app
    result = send(client, sid, "我用 Win11，连接校园 WiFi，微信能用，但是所有网页打不开。")
    env = result["environment_profile"]
    assert (env["os_family"],env["network_access"],env["affected_scope"]) == ("windows","campus_wifi","web_only")
    assert result["ui_action"]["type"] == "client_check"
    changed = client.patch("/api/session/environment/user", json={"session_id":sid,"network_access":"campus_wired"})
    assert changed.status_code == 200 and changed.json()["field_sources"]["network_access"]["source"] == "user"
    assert client.get(f"/api/session/{sid}").json()["environment_profile"]["network_access"] == "campus_wired"


def test_tc01_knowledge_and_tc09_hypothetical_do_not_request_context(context_app):
    _, client, _, sid, tools, llm = context_app
    for message in ["eduroam 是什么？", "如果一个同学用 Windows 连校园 WiFi，网页打不开怎么办？"]:
        result = send(client, sid, message)
        assert result["ui_action"] is None and result["metrics"]["response_mode"] == "knowledge"
        assert result["environment_profile"]["network_access"] == "unknown"
        assert result["metrics"]["network_tool_calls"] == 0
    assert tools.handler_calls == 0 and llm.calls


def test_knowledge_uses_existing_rag_without_context_model_call():
    from test_knowledge_finalization import LLM, Retriever, completed
    llm = LLM([completed()])
    agent = AgentOrchestrator(llm, ToolRegistry(FixtureOnlyTools(), Retriever()))
    result = agent.run("天津大学 VPN 怎么使用？")
    assert result.ui_action is None and result.rag_calls == 1
    assert len(result.sources) == 3 and len(llm.calls) == 2
    assert [step.tool_name for step in result.steps] == ["knowledge_search"]


def test_tc12_legacy_task_and_history_default(context_app):
    from netpilot.agent.task_state import SessionTaskState
    from netpilot.models import DiagnosisRecordView
    task = SessionTaskState.model_validate({"session_id":str(uuid4()),"owner_user_id":str(uuid4())})
    assert not task.context_acquisition.asked_fields
    _, client, _, sid, *_ = context_app
    result = send(client, sid, "网页打不开")
    payload = client.get(f'/api/diagnoses/{result["record_id"]}').json()
    payload.pop("context_acquisition")
    legacy = DiagnosisRecordView.model_validate(payload)
    assert legacy.context_acquisition.asked_fields == []
    assert legacy.context_acquisition.unknown_fields == []
    assert legacy.context_acquisition.last_question_field is None


def test_cross_user_and_stale_replay(context_app):
    app, alice, _, sid, *_ = context_app
    send(alice, sid, "网页打不开")
    payload = {"session_id":sid,"message":"answer","context_answer":{"field":"affected_scope","value":"web_only"}}
    bob = TestClient(app)
    register_test_user(bob)
    assert bob.post("/api/chat", json=payload).status_code == 404
    assert alice.post("/api/chat", json=payload).status_code == 200
    assert alice.post("/api/chat", json=payload).status_code == 409
