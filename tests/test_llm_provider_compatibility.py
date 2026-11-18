"""Provider compatibility through the real SDK and an offline HTTP transport."""

import json
import logging
from collections import deque

import httpx
import pytest
from fastapi.testclient import TestClient

from netpilot.agent import AgentOrchestrator, AgentStatus, FallbackReason, ToolRegistry
from netpilot.agent.knowledge import citation_refs
from netpilot.config import Settings
from netpilot.llm import ChatMessage, ChatRole, FunctionCall, LLMRequestError, LLMServiceError, TJUClient, ToolCall
from netpilot.main import create_app
from netpilot.tools import build_network_tools

from test_knowledge_429_api import CampusFixture, ask, assert_knowledge_only, start_session
from test_knowledge_finalization import Retriever, citation
from test_netpilot_llm import make_settings, messages
from test_tju_429_retries import completion, error_response, use_mock_transport


MODEL = "fixture/model-v7"
SECRET = "offline-provider-credential"
PRIVATE = "PRIVATE_PROVIDER_BODY_AND_REASONING"


def settings(**overrides):
    return make_settings(**{
        "llm_provider": "deepseek", "llm_api_base": "https://compatible.example.test",
        "llm_api_key": SECRET, "llm_model": MODEL, **overrides,
    })


def reply(content, *, finish="stop", reasoning=None, tool_calls=None):
    payload = completion(content)
    payload["model"] = MODEL
    choice = payload["choices"][0]
    choice["finish_reason"] = finish
    if reasoning is not None:
        choice["message"]["reasoning_content"] = reasoning
    if tool_calls is not None:
        choice["message"]["tool_calls"] = tool_calls
    return httpx.Response(200, json=payload, headers={"x-ds-request-id": "fixture-request"})


@pytest.fixture
def scripted(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="netpilot")

    def create(*responses):
        pending = deque(responses)
        requests = []

        def respond(request):
            assert str(request.url) == "https://compatible.example.test/chat/completions"
            assert request.headers["authorization"] == f"Bearer {SECRET}"
            body = json.loads(request.content)
            assert body["model"] == MODEL
            assert body["thinking"] == {"type": "disabled"}
            assert "temperature" not in body
            requests.append(body)
            assert pending, "unexpected extra provider request"
            return pending.popleft()

        use_mock_transport(monkeypatch, respond)
        return requests

    return create


def run_knowledge():
    config = settings()
    client = TJUClient(config)
    try:
        return AgentOrchestrator(client, ToolRegistry(build_network_tools(config), Retriever())).run("VPN 是什么？")
    finally:
        client.close()


def finalization_logs(caplog):
    return [item for record in caplog.records if record.name == "netpilot.agent.orchestrator"
            if (item := json.loads(record.message))["event"] == "knowledge_finalization"]


def test_dotenv_neutral_config_and_legacy_key_isolation(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TJU_API_KEY=legacy-key\nTJU_MODEL=tju-llm\nLLM_PROVIDER=deepseek\n"
                        "LLM_API_BASE=https://compatible.example.test/\nLLM_MODEL=fixture/model-v7\n", encoding="utf-8")
    config = Settings(_env_file=env_file)
    assert config.effective_llm_model == MODEL
    assert config.effective_llm_api_base == "https://compatible.example.test"
    assert not config.llm_configured and config.effective_llm_api_key is None
    assert not make_settings(llm_api_base="https://different.example.test").llm_configured
    assert make_settings(llm_api_key="", llm_api_base="", llm_model="").llm_configured
    assert settings().llm_configured


def test_plain_completion_does_not_expose_reasoning(scripted):
    requests = scripted(reply("你好", reasoning=PRIVATE))
    client = TJUClient(settings())
    try:
        result = client.chat([ChatMessage(role=ChatRole.USER, content="你好")])
    finally:
        client.close()
    assert result.content == "你好" and result.has_reasoning_content
    assert result.finish_reason == "stop" and result.request_id == "fixture-request"
    assert result.model == MODEL and len(requests) == 1
    assert PRIVATE not in result.model_dump_json()


def test_deepseek_native_function_call_can_continue_without_replaying_reasoning(scripted):
    call = ToolCall(id="fixture-call", function=FunctionCall(name="knowledge_search", arguments='{"query":"VPN"}'))
    requests = scripted(reply(None, finish="tool_calls", reasoning=PRIVATE, tool_calls=[call.model_dump()]), reply("已参考资料。"))
    client = TJUClient(settings())
    tools = [{"type": "function", "function": {"name": "knowledge_search"}}]
    try:
        first = client.chat(messages(), tools=tools)
        second = client.chat([
            *messages(), ChatMessage(role=ChatRole.ASSISTANT, tool_calls=first.tool_calls),
            ChatMessage(role=ChatRole.TOOL, tool_call_id=call.id, content="fixture evidence"),
        ])
    finally:
        client.close()
    assert first.tool_calls == [call] and second.content == "已参考资料。"
    assert requests[0]["tools"] == tools and "tools" not in requests[1]
    assert PRIVATE not in json.dumps(requests)
    assert requests[1]["messages"][-1]["tool_call_id"] == call.id


@pytest.mark.parametrize(("body", "mode", "kind", "source_indexes"), [
    ("VPN 用于访问校内资源。", "source_panel_only", "citation_missing", [0, 1, 2]),
    ("VPN 用于访问校内资源。[S1]", "inline", None, [0]),
    ("VPN 用于访问校内资源。【S2】" + citation(1) + "[S99]", "inline", "citation_partial", [1]),
    ("VPN 用于访问校内资源。" + citation(0, 2), "inline", None, [0, 2]),
])
def test_knowledge_accepts_grounded_text_and_maps_only_selected_refs(scripted, caplog, body, mode, kind, source_indexes):
    requests = scripted(reply(body))
    result = run_knowledge()
    assert result.status is AgentStatus.COMPLETED and result.fallback_reason is None
    assert result.citation_mode == mode and result.knowledge_finalization_failure_kind == kind
    assert "VPN 用于访问校内资源。" in result.answer and "[S99]" not in result.answer
    assert [source.source for source in result.sources] == [f"https://example.test/{index}" for index in source_indexes]
    assert len(citation_refs(result.answer)) == (0 if mode == "source_panel_only" else len(source_indexes))
    if kind == "citation_partial":
        assert result.answer.count(citation(1)) == 1 and result.sources[0].source_type.value == "community"
    assert len(requests) == len(result.steps) == 1
    request = requests[0]
    assert "tools" not in request and "tool_choice" not in request
    assert all(f"[SOURCE] [S{index}]" in request["messages"][0]["content"] for index in range(1, 4))
    assert "source_ref=" not in request["messages"][0]["content"]
    log, = finalization_logs(caplog)
    assert (log["provider"], log["model"], log["success"], log["failure_kind"]) == ("deepseek", MODEL, True, kind)
    assert log["invalid_citation_count"] == (1 if kind == "citation_partial" else 0)
    assert log["provider_request_id"] == "fixture-request" and log["citation_mode"] == mode


def test_unknown_citation_has_one_directed_retry_then_falls_back(scripted, caplog):
    requests = scripted(*[reply("VPN 用于访问校内资源。[S99]") for _ in range(2)])
    result = run_knowledge()
    assert result.fallback_reason is FallbackReason.FINALIZATION_FAILED
    assert result.knowledge_finalization_failure_kind == "citation_invalid"
    assert "[S99]" not in result.answer and len(result.sources) == 3
    assert "请使用当前片段旁的 [S1] / [S2]" in requests[1]["messages"][0]["content"]
    logs = finalization_logs(caplog)
    assert [item["invalid_citation_count"] for item in logs] == [1, 1]
    assert logs[0]["selected_context_chars"] == logs[1]["selected_context_chars"]


@pytest.mark.parametrize(("finish", "body", "reasoning", "kind", "retry"), [
    ("stop", "", PRIVATE, "model_empty_final_content", True),
    ("stop", None, None, "model_empty", True),
    ("length", "截断的正文", None, "model_length", True),
    ("content_filter", "不应展示的正文", None, "model_content_filter", False),
    ("tool_calls", None, None, "model_tool_call", True),
    ("insufficient_system_resource", None, None, "model_insufficient_system_resource", True),
    ("aborted", None, None, "model_aborted", True),
    ("stop", "[official] 未知标题\nhttps://invented.example.test", None, "source_only", True),
    ("stop", "可通过[此处](//invented.example.test)访问内网。[S1]", None, "model_external_link", True),
])
def test_finish_reason_and_bad_body_are_diagnosed_before_trying_again(scripted, caplog, finish, body, reasoning, kind, retry):
    responses = [reply(body, finish=finish, reasoning=reasoning)]
    if retry:
        responses.append(reply("VPN 用于访问校内资源。[S1]"))
    requests = scripted(*responses)
    result = run_knowledge()
    logs = finalization_logs(caplog)
    assert len(requests) == len(logs) == result.knowledge_finalization_attempts == (2 if retry else 1)
    assert logs[0]["failure_kind"] == result.knowledge_finalization_failure_kind == kind
    assert logs[0]["finish_reason"] == finish and logs[0]["has_reasoning_content"] is bool(reasoning)
    assert PRIVATE not in caplog.text and PRIVATE not in result.answer
    if retry:
        assert logs[1]["success"] and logs[1]["selected_context_chars"] < logs[0]["selected_context_chars"]
        assert result.fallback_reason is None
    else:
        assert result.fallback_reason is FallbackReason.FINALIZATION_FAILED
        assert body not in result.answer


@pytest.mark.parametrize(("status", "code", "error_cls"), [
    (200, "server_error", LLMServiceError), (200, "model_not_found", LLMRequestError),
    (400, "invalid_parameter", LLMRequestError), (404, "model_not_found", LLMRequestError),
])
def test_provider_error_metadata_is_typed_safe_and_keeps_actual_http_status(scripted, caplog, status, code, error_cls):
    def provider_response():
        return error_response(status, {"retry-after": "2"}, code=code, kind="api_error")

    requests = scripted(provider_response(), provider_response())
    client = TJUClient(settings())
    try:
        with pytest.raises(error_cls) as caught:
            client.chat(messages())
    finally:
        client.close()
    exc = caught.value
    assert (exc.status_code, exc.provider_error_code, exc.provider_error_type) == (status, code, "api_error")
    assert exc.attempts_made == 1 and exc.request_id == "upstream-1" and exc.retry_after_seconds == 2
    assert exc.__cause__ is None and exc.__context__ is None
    result = run_knowledge()
    log, = finalization_logs(caplog)
    assert log["provider_error_code"] == code and log["status_code"] == status
    assert log["failure_kind"] == "model_request_failed" and log["llm_error_type"] == error_cls.__name__
    assert len(requests) == 2 and result.knowledge_finalization_attempts == 1
    assert result.fallback_reason is FallbackReason.LLM_ERROR and result.sources
    assert ("兼容性问题" if error_cls is LLMRequestError else "模型暂时无法完成整理") in result.answer
    assert all(value not in caplog.text + str(exc) + result.answer for value in (SECRET, "PRIVATE_BODY", "unit-test-secret"))


def test_error_envelope_takes_priority_over_choices_and_filters_secret_metadata(scripted, caplog):
    body = completion("This must not be accepted")
    body.update(error={"message": PRIVATE, "code": SECRET, "type": "contains unsafe whitespace"}, usage={})
    scripted(httpx.Response(200, json=body, headers={"x-request-id": SECRET}))
    result = run_knowledge()
    log, = finalization_logs(caplog)
    assert not log["success"] and log["failure_kind"] == "model_request_failed"
    assert log["provider_request_id"] is log["provider_error_code"] is log["provider_error_type"] is None
    assert all(value not in caplog.text + result.answer for value in (SECRET, PRIVATE, "This must not be accepted"))


def test_three_new_sessions_keep_knowledge_flow_and_sources_in_chat_and_sse(scripted, monkeypatch, tmp_path):
    questions = ("eduroam 是什么？", "天津大学 VPN 怎么使用？", "VPN 客户端具体怎么安装？")
    answers = ("eduroam 的接入方式需要核对学校资料。[S1]", "VPN 的认证方式以校方说明为准。",
               "安装客户端前，请核对版本及适用平台。【S1】")
    requests = scripted(*(reply(content) for content in answers))
    trace = []
    monkeypatch.setattr("netpilot.main.load_configured_retriever", lambda config: CampusFixture(trace))
    app = create_app(settings(diagnosis_history_enabled=True, diagnosis_db_path=tmp_path / "providers.db"))
    with TestClient(app) as client:
        start_session(client)
        for index, question in enumerate(questions):
            session = client.post("/api/session").json()["session_id"]
            result = ask(client, "/api/chat/stream" if index == 1 else "/api/chat", session, question)
            assert_knowledge_only(result)
            assert result["metrics"]["knowledge_finalization_attempts"] == 1
            assert result["metrics"]["fallback_reason"] is None
            assert result["metrics"]["citation_mode"] == ("source_panel_only" if index == 1 else "inline")
            assert [step["tool_name"] for step in result["tool_calls"]] == ["knowledge_search"]
            assert result["sources"][0]["source_type"] == "community"
            if index == 1:
                record_id = client.get("/api/diagnoses").json()["items"][0]["record_id"]
                record = client.get(f"/api/diagnoses/{record_id}").json()
                turn, = record["conversation_turns"]
                assert turn["citation_mode"] == "source_panel_only"
                assert turn["source_refs"] == [result["sources"][0]["source_ref"]]
    assert trace == [("rag", question) for question in questions]
    assert [request["messages"][-1]["content"] for request in requests] == list(questions)
