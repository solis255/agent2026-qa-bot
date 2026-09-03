"""Small, safe Server-Sent Events protocol for streamed chat responses."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextvars import Context, copy_context
from queue import Empty, Queue
from threading import Thread
from typing import Any, Literal
from uuid import UUID

from netpilot.models import ChatResponse


SSEEventName = Literal["start", "delta", "complete", "error"]
_SAFE_STREAM_ERROR = {
    "schema_version": 1,
    "code": "stream_failed",
    "message": "诊断请求处理失败，请稍后重试。",
    "retryable": True,
}


def encode_sse_event(
    event: SSEEventName,
    data: dict[str, Any],
    *,
    event_id: int,
) -> bytes:
    """Encode one JSON-only SSE event without allowing line injection."""

    serialized = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {event_id}\nevent: {event}\ndata: {serialized}\n\n".encode("utf-8")


def iter_chat_sse(
    session_id: UUID,
    run_turn: Callable[[], ChatResponse],
    *,
    chunk_chars: int = 32,
    heartbeat_seconds: float = 15.0,
    context: Context | None = None,
) -> Iterator[bytes]:
    """Run one turn in a worker and stream a bounded, versioned event sequence.

    The worker owns session finalization, so closing the client iterator cannot
    leave a conversation permanently busy.
    """

    chunk_size = max(1, min(int(chunk_chars), 256))
    heartbeat = max(1.0, min(float(heartbeat_seconds), 30.0))
    completed: Queue[tuple[Literal["complete", "error"], ChatResponse | None]] = (
        Queue(maxsize=1)
    )

    def worker() -> None:
        try:
            completed.put(("complete", run_turn()))
        except Exception:
            completed.put(("error", None))

    worker_context = context or copy_context()
    Thread(
        target=worker_context.run,
        args=(worker,),
        name="netpilot-sse-turn",
        daemon=True,
    ).start()

    def events() -> Iterator[bytes]:
        sequence = 0
        yield encode_sse_event(
            "start",
            {
                "schema_version": 1,
                "session_id": str(session_id),
            },
            event_id=sequence,
        )
        sequence += 1

        while True:
            try:
                outcome, response = completed.get(timeout=heartbeat)
                break
            except Empty:
                yield b": keep-alive\n\n"

        if outcome == "error" or response is None:
            yield encode_sse_event("error", _SAFE_STREAM_ERROR, event_id=sequence)
            return

        answer = response.answer
        for offset in range(0, len(answer), chunk_size):
            yield encode_sse_event(
                "delta",
                {
                    "schema_version": 1,
                    "sequence": offset // chunk_size,
                    "text": answer[offset : offset + chunk_size],
                },
                event_id=sequence,
            )
            sequence += 1

        yield encode_sse_event(
            "complete",
            {
                "schema_version": 1,
                "response": response.model_dump(mode="json"),
            },
            event_id=sequence,
        )

    return events()
