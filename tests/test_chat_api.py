from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from netpilot.agent import AgentResult, AgentStatus, AgentToolStep
from netpilot.config import Settings
from netpilot.main import create_app
from netpilot.rag import KnowledgeSource
from netpilot.tools.schemas import DNSLookupData, ToolResult


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, message: str, *, history=()) -> AgentResult:
        self.calls.append({"message": message, "history": list(history)})
        return AgentResult(
            answer="问题判断：DNS 解析异常。\n建议：检查 DNS 设置。",
            status=AgentStatus.COMPLETED,
            tool_rounds=1,
            steps=[
                AgentToolStep(
                    round=1,
                    tool_call_id="call_dns_web",
                    tool_name="dns_lookup",
                    arguments={"domain": "github.com"},
                    result=ToolResult[DNSLookupData](
                        success=True,
                        tool="dns_lookup",
                        summary="域名解析失败",
                        data=DNSLookupData(resolved=False, addresses=[]),
                        error=None,
                        duration_ms=2,
                    ),
                )
            ],
            sources=[
                KnowledgeSource(
                    title="VPN 社区资料",
                    source="https://wiki.tjubot.cn/e-life/vpn",
                    source_type="community",
                    file="campus_vpn.md",
                    chunk_id="vpn_chunk_web",
                    score=0.88,
                )
            ],
        )


class BrokenAgent:
    def run(self, message: str, *, history=()):
        raise RuntimeError("secret backend detail")


def build_application(*, api_key: str | None = "web-test-key", **overrides):
    values = {
        "_env_file": None,
        "tju_api_key": api_key,
        "tool_mode": "mock",
        "rag_enabled": False,
    }
    values.update(overrides)
    application = create_app(Settings(**values))
    application.state.agent = FakeAgent()
    return application


def create_session(client: TestClient) -> str:
    response = client.post("/api/session")
    assert response.status_code == 201
    return response.json()["session_id"]


def test_chat_api_returns_structured_timeline_and_sources() -> None:
    application = build_application()
    with TestClient(application) as client:
        session_id = create_session(client)
        response = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "github.com 为什么打不开？"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["diagnosis"]["status"] == "completed"
    assert body["diagnosis"]["evidence"] == [
        {"tool": "dns_lookup", "status": "abnormal", "summary": "域名解析失败"}
    ]
    tool = body["tool_calls"][0]
    assert tool["tool_call_id"] == "call_dns_web"
    assert tool["success"] is True
    assert tool["finding_status"] == "abnormal"
    assert body["sources"][0]["source"].endswith("/vpn")
    assert "web-test-key" not in response.text


def test_chat_api_passes_bounded_session_history_to_agent() -> None:
    application = build_application(max_history_messages=2)
    fake_agent = application.state.agent
    with TestClient(application) as client:
        session_id = create_session(client)
        for message in ("第一问", "第二问"):
            assert client.post(
                "/api/chat",
                json={"session_id": session_id, "message": message},
            ).status_code == 200

    second_history = fake_agent.calls[1]["history"]
    assert [message.content for message in second_history] == [
        "第一问",
        "问题判断：DNS 解析异常。\n建议：检查 DNS 设置。",
    ]
    assert len(application.state.sessions.history(UUID(session_id))) == 2


def test_chat_api_handles_unknown_busy_and_unconfigured_sessions() -> None:
    application = build_application()
    with TestClient(application) as client:
        unknown = client.post(
            "/api/chat",
            json={"session_id": "27929b0e-5680-49ca-9d2b-feb153c13a40", "message": "测试"},
        )
        session_id = create_session(client)
        application.state.sessions.begin_turn(UUID(session_id))
        busy = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "测试"},
        )
        application.state.sessions.abort_turn(UUID(session_id))

    unconfigured = build_application(api_key=None)
    with TestClient(unconfigured) as client:
        no_key_session = create_session(client)
        no_key = client.post(
            "/api/chat",
            json={"session_id": no_key_session, "message": "测试"},
        )

    assert unknown.status_code == 404
    assert busy.status_code == 409
    assert no_key.status_code == 503


def test_chat_api_validates_messages_and_hides_unexpected_errors() -> None:
    application = build_application()
    application.state.agent = BrokenAgent()
    with TestClient(application) as client:
        session_id = create_session(client)
        empty = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "   "},
        )
        too_long = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "x" * 4001},
        )
        failed = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "触发异常"},
        )

    assert empty.status_code == 422
    assert too_long.status_code == 422
    assert failed.status_code == 500
    assert "secret backend detail" not in failed.text
    assert application.state.sessions.get(UUID(session_id)).busy is False
