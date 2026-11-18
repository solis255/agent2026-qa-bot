"""Production Chat/SSE, registry, session, history, and SDK on offline responses."""
import json

from fastapi.testclient import TestClient
import httpx
import pytest

from netpilot.main import create_app
from netpilot.rag import KnowledgeSearchResult
from netpilot.rag.schemas import source_ref_for
from conftest import register_test_user
from test_chat_stream import parse_sse
from test_netpilot_llm import make_settings
from test_tju_429_retries import collect_attempts, completion, error_response, use_mock_transport


EDUROAM = "eduroam 是什么？"
VPN = "天津大学 VPN 怎么使用？"
IPV6 = "校园网 IPv6 有什么作用？"


class CampusFixture:
    def __init__(self, trace, *, empty=False):
        self.trace = trace
        self.empty = empty

    def search(self, query, top_k=None):
        self.trace.append(("rag", query))
        if self.empty:
            return []
        topic = "eduroam" if "eduroam" in query.lower() else "ipv6" if "ipv6" in query.lower() else "vpn"
        return [KnowledgeSearchResult(
            title=f"{topic} 参考资料", source=f"https://example.test/{topic}",
            source_type="community", file=f"{topic}.md", chunk_id=f"{topic}-1",
            content=f"{topic} 的本地资料片段。实际用法请核验校方官方说明。", score=0.9,
        )]


def topic_for(question):
    return "eduroam" if "eduroam" in question.lower() else "ipv6" if "ipv6" in question.lower() else "vpn"


@pytest.fixture
def campus_app(monkeypatch, tmp_path):
    def create(codes=(), *, empty=False):
        trace, attempts = [], []
        remaining = iter(codes)

        def respond(req):
            body = json.loads(req.content)
            assert "tools" not in body and "tool_choice" not in body and body["stream"] is False
            question = body["messages"][-1]["content"]
            topic = topic_for(question)
            trace.append(("http", question))
            attempts.append(body)
            outcome = next(remaining, 200)
            if outcome != 200:
                return error_response(429, {"retry-after-ms": "250"},
                                      code="insufficient_quota" if outcome == "quota" else "temporary_limit",
                                      attempt=len(attempts))
            ref = source_ref_for(f"https://example.test/{topic}", f"{topic}-1")
            assert f"source_ref={ref}" in body["messages"][0]["content"]
            return httpx.Response(200, json=completion(f"{topic}：可以先核对该服务的适用场景和认证方式。[[cite:{ref}]]"))

        waits = use_mock_transport(monkeypatch, respond)
        monkeypatch.setattr("netpilot.main.load_configured_retriever", lambda _: CampusFixture(trace, empty=empty))
        app = create_app(make_settings(
            tool_mode="mock", diagnosis_history_enabled=True, diagnosis_db_path=tmp_path / "fixture.db",
            reasoning_summary_llm_enabled=True,
        ))
        return app, trace, waits
    return create


def ask(client, endpoint, sid, question, *, request_id="test-tju-knowledge"):
    response = client.post(endpoint, json={"session_id": sid, "message": question},
                           headers={"X-Request-ID": request_id})
    assert response.status_code == 200, response.text
    assert response.headers["x-request-id"] == request_id
    if endpoint.endswith("/stream"):
        assert "text/event-stream" in response.headers["content-type"]
        return next(item["data"]["response"] for item in parse_sse(response.text) if item["event"] == "complete")
    return response.json()


def start_session(client):
    register_test_user(client)
    return client.post("/api/session").json()["session_id"]


def assert_knowledge_only(result):
    assert result["diagnostic_readiness"]["state"] == "knowledge_only"
    assert result["ui_action"] is None
    assert result["metrics"]["response_mode"] == "knowledge"
    assert result["metrics"]["network_tool_calls"] == 0
    assert result["diagnosis"]["evidence"] == []
    assert not result["metrics"]["reasoning_summary_llm_used"]


def test_eduroam_vpn_and_ipv6_use_distinct_sources_with_one_synthesis_each(campus_app):
    app, trace, waits = campus_app()
    with TestClient(app) as client:
        sid = start_session(client)
        for endpoint, question in [("/api/chat", EDUROAM), ("/api/chat/stream", VPN), ("/api/chat", IPV6)]:
            result = ask(client, endpoint, sid, question)
            assert_knowledge_only(result)
            assert result["diagnosis"]["status"] == "completed"
            assert result["metrics"]["knowledge_finalization_attempts"] == result["metrics"]["rag_calls"] == 1
            assert result["metrics"]["fallback_reason"] is None
            assert [step["tool_name"] for step in result["tool_calls"]] == ["knowledge_search"]
            assert len(result["sources"]) == 1 and result["sources"][0]["source_type"] == "community"
            assert result["sources"][0]["source"].endswith("/" + topic_for(question))
            assert f"[[cite:{result['sources'][0]['source_ref']}]]" in result["answer"]
            assert any(s["decision"] == "knowledge_finalization" for s in result["reasoning_trace"])
        record = client.get(f"/api/diagnoses/{result['record_id']}").json()
        assert record["turn_count"] == 3
        assert all(step["finding_status"] == "reference" for step in record["tool_calls"])
        assert len(record["sources"]) == 3
    assert trace == [(action, q) for q in (EDUROAM, VPN, IPV6) for action in ("rag", "http")]
    assert waits == []


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream"])
@pytest.mark.parametrize(("codes", "expected_waits", "kind"), [
    ([429, 200], 1, None),
    ([429, 429, 429], 2, "llm_rate_limited"),
    (["quota"], 0, "llm_quota_exhausted"),
])
def test_retry_fallback_and_recovery_use_same_policy_in_chat_and_sse(campus_app, caplog, endpoint, codes, expected_waits, kind):
    app, trace, waits = campus_app(codes)
    with TestClient(app) as client:
        sid = start_session(client)
        result = ask(client, endpoint, sid, EDUROAM, request_id="test-429-first")
        assert_knowledge_only(result)
        assert result["metrics"]["knowledge_finalization_attempts"] == 1
        assert result["metrics"]["knowledge_finalization_failure_kind"] == kind
        assert result["metrics"]["fallback_reason"] == ("llm_rate_limited" if kind else None)
        assert trace == [("rag", EDUROAM)] + [("http", EDUROAM)] * len(codes)
        assert len(result["sources"]) == 1
        answer = result["answer"]
        if kind:
            assert "原文片段" in answer and "尚未经过模型完整整理" in answer
            assert ("配额可能已耗尽" in answer) == (kind == "llm_quota_exhausted")
            assert ("有限次数的重试" in answer) == (kind == "llm_rate_limited")
        else:
            assert "429" not in answer and "原文片段" not in answer
        record = client.get(f"/api/diagnoses/{result['record_id']}/report").json()
        assert record["sources"][0]["source_type"] == "community"
        second = ask(client, endpoint, sid, VPN, request_id="test-429-recovered")
        assert_knowledge_only(second)
        assert second["metrics"]["fallback_reason"] is None and second["sources"][0]["source"].endswith("/vpn")
    assert trace[-2:] == [("rag", VPN), ("http", VPN)]
    assert waits == [0.25] * expected_waits
    logs = collect_attempts(caplog)
    assert [event["request_id"] for event in logs] == ["test-429-first"] * len(codes) + ["test-429-recovered"]
    assert all(event["session_id"] == sid for event in logs)
    assert logs[0]["provider_request_id"] == "upstream-1"
    assert "PRIVATE_BODY" not in caplog.text and "unit-test-secret" not in caplog.text


def test_empty_rag_does_not_call_even_an_unavailable_model_or_invent_sources(campus_app):
    app, trace, waits = campus_app([429], empty=True)
    with TestClient(app) as client:
        result = ask(client, "/api/chat/stream", start_session(client), EDUROAM)
    assert_knowledge_only(result)
    assert result["diagnosis"]["status"] == "insufficient_sources"
    assert result["metrics"]["fallback_reason"] == "knowledge_no_sources"
    assert result["metrics"]["knowledge_finalization_attempts"] == 0
    assert not result["sources"] and "[[cite:" not in result["answer"] and "429" not in result["answer"]
    assert "没有提供足够来源" in result["answer"]
    assert trace == [("rag", EDUROAM)] and waits == []


def test_same_normalized_query_reuses_session_evidence_without_another_search(campus_app):
    app, trace, _ = campus_app()
    duplicate = "EDUROAM   是什么?"
    with TestClient(app) as client:
        sid = start_session(client)
        first = ask(client, "/api/chat", sid, EDUROAM)
        result = ask(client, "/api/chat/stream", sid, duplicate)
    assert_knowledge_only(result)
    assert result["sources"] == first["sources"]
    assert result["tool_calls"] == [] and result["metrics"]["rag_calls"] == 0
    assert any(step["title"] == "复用同一知识查询" for step in result["reasoning_trace"])
    assert trace == [("rag", EDUROAM), ("http", EDUROAM), ("http", duplicate)]
