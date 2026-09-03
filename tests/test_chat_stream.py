from __future__ import annotations

import json
from threading import Event
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from netpilot.agent import AgentResult, AgentStatus, AgentToolStep
from netpilot.api.sse import encode_sse_event, iter_chat_sse
from netpilot.config import Settings
from netpilot.main import create_app
from netpilot.models import ChatResponse, DiagnosisView
from netpilot.tools.schemas import DNSLookupData, ToolResult


ANSWER = "问题判断：DNS 解析异常。\n建议操作：检查 DNS 设置后重新解析域名。"


class StreamAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, message: str, *, history=()) -> AgentResult:
        self.calls.append({"message": message, "history": list(history)})
        return AgentResult(
            answer=ANSWER,
            status=AgentStatus.COMPLETED,
            tool_rounds=1,
            steps=[
                AgentToolStep(
                    round=1,
                    tool_call_id="stream_dns",
                    tool_name="dns_lookup",
                    arguments={"domain": "github.com"},
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


class BrokenStreamAgent:
    def run(self, message: str, *, history=()) -> AgentResult:
        raise RuntimeError("secret streaming backend detail")


def stream_app(tmp_path, *, api_key: str | None = "stream-test-key"):
    application = create_app(
        Settings(
            _env_file=None,
            tju_api_key=api_key,
            tool_mode="mock",
            rag_enabled=False,
            diagnosis_history_enabled=True,
            diagnosis_db_path=tmp_path / "stream.db",
            sse_chunk_chars=8,
            sse_heartbeat_seconds=1,
        )
    )
    application.state.agent = StreamAgent()
    return application


def create_session(client: TestClient) -> str:
    response = client.post("/api/session")
    assert response.status_code == 201
    return response.json()["session_id"]


def parse_sse(payload: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in payload.replace("\r\n", "\n").split("\n\n"):
        if not block or block.startswith(":"):
            continue
        event_name = "message"
        event_id = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("id: "):
                event_id = int(line[4:])
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        events.append(
            {
                "event": event_name,
                "id": event_id,
                "data": json.loads("\n".join(data_lines)),
            }
        )
    return events


def minimal_response(answer: str = "完成") -> ChatResponse:
    return ChatResponse(
        session_id=uuid4(),
        answer=answer,
        diagnosis=DiagnosisView(
            status=AgentStatus.COMPLETED,
            summary=answer,
            tool_rounds=0,
        ),
    )


def test_stream_api_emits_versioned_deltas_and_complete_snapshot(tmp_path) -> None:
    application = stream_app(tmp_path)
    agent = application.state.agent
    with TestClient(application) as client:
        session_id = create_session(client)
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"session_id": session_id, "message": "github.com 无法解析"},
        ) as response:
            payload = "".join(response.iter_text())

        history = application.state.sessions.history(UUID(session_id))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-content-type-options"] == "nosniff"
    events = parse_sse(payload)
    assert events[0]["event"] == "start"
    assert events[0]["data"] == {"schema_version": 1, "session_id": session_id}
    assert events[-1]["event"] == "complete"
    assert [item["id"] for item in events] == list(range(len(events)))
    deltas = [item["data"]["text"] for item in events if item["event"] == "delta"]
    assert len(deltas) > 1
    assert "".join(deltas) == ANSWER
    completed = ChatResponse.model_validate(events[-1]["data"]["response"])
    assert completed.answer == ANSWER
    assert completed.record_id is not None
    assert completed.tool_calls[0].finding_status == "abnormal"
    assert [message.content for message in history] == ["github.com 无法解析", ANSWER]
    assert len(agent.calls) == 1
    assert "stream-test-key" not in payload


def test_stream_api_prevalidates_sessions_and_configuration(tmp_path) -> None:
    application = stream_app(tmp_path)
    with TestClient(application) as client:
        unknown = client.post(
            "/api/chat/stream",
            json={"session_id": str(uuid4()), "message": "测试"},
        )
        session_id = create_session(client)
        application.state.sessions.begin_turn(UUID(session_id))
        busy = client.post(
            "/api/chat/stream",
            json={"session_id": session_id, "message": "测试"},
        )
        application.state.sessions.abort_turn(UUID(session_id))

    unconfigured = stream_app(tmp_path, api_key=None)
    with TestClient(unconfigured) as client:
        no_key_session = create_session(client)
        no_key = client.post(
            "/api/chat/stream",
            json={"session_id": no_key_session, "message": "测试"},
        )

    assert unknown.status_code == 404
    assert busy.status_code == 409
    assert no_key.status_code == 503


def test_stream_worker_error_is_safe_and_releases_busy_session(tmp_path) -> None:
    application = stream_app(tmp_path)
    application.state.agent = BrokenStreamAgent()
    with TestClient(application) as client:
        session_id = create_session(client)
        response = client.post(
            "/api/chat/stream",
            json={"session_id": session_id, "message": "触发错误"},
        )
        snapshot = application.state.sessions.get(UUID(session_id))

    events = parse_sse(response.text)
    assert response.status_code == 200
    assert [item["event"] for item in events] == ["start", "error"]
    assert events[-1]["data"]["code"] == "stream_failed"
    assert events[-1]["data"]["retryable"] is True
    assert "secret streaming backend detail" not in response.text
    assert snapshot.busy is False
    assert snapshot.message_count == 0


def test_sse_json_encoding_prevents_event_line_injection() -> None:
    encoded = encode_sse_event(
        "delta",
        {"schema_version": 1, "text": "安全文本\nevent: hacked\ndata: leaked"},
        event_id=2,
    ).decode("utf-8")

    assert encoded.splitlines()[1] == "event: delta"
    assert "event: hacked" not in encoded.splitlines()
    assert len(parse_sse(encoded)) == 1


def test_sse_emits_heartbeat_and_worker_survives_closed_iterator() -> None:
    gate = Event()
    started = Event()
    finished = Event()

    def delayed_turn() -> ChatResponse:
        started.set()
        gate.wait(timeout=3)
        finished.set()
        return minimal_response("延迟完成")

    iterator = iter_chat_sse(
        uuid4(),
        delayed_turn,
        chunk_chars=4,
        heartbeat_seconds=1,
    )
    assert started.wait(timeout=1) is True
    assert b"event: start" in next(iterator)
    assert next(iterator) == b": keep-alive\n\n"
    iterator.close()
    gate.set()

    assert finished.wait(timeout=2) is True
