"""Request-scoped, redacted JSON logging for NetPilot."""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar, Token
from time import perf_counter
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response


_request_id: ContextVar[str] = ContextVar("netpilot_request_id", default="-")
_session_id: ContextVar[str] = ContextVar("netpilot_session_id", default="-")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
}


def configure_observability(level: str) -> None:
    application_logger = logging.getLogger("netpilot")
    application_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not any(
        getattr(handler, "_netpilot_structured", False)
        for handler in application_logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._netpilot_structured = True  # type: ignore[attr-defined]
        application_logger.addHandler(handler)


def get_request_id() -> str:
    return _request_id.get()


def get_session_id() -> str:
    return _session_id.get()


def set_session_id(value: object) -> Token[str]:
    return _session_id.set(str(value))


def reset_session_id(token: Token[str]) -> None:
    _session_id.reset(token)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    payload = {
        "event": event,
        "request_id": get_request_id(),
        "session_id": get_session_id(),
        **fields,
    }
    logger.log(
        level,
        json.dumps(_redact(payload), ensure_ascii=False, separators=(",", ":")),
    )


async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if _REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
    request_token = _request_id.set(request_id)
    session_token = _session_id.set("-")
    started = perf_counter()
    http_status = 500
    error_type: str | None = None
    try:
        response = await call_next(request)
        http_status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        error_type = type(exc).__name__
        raise
    finally:
        log_event(
            logging.getLogger("netpilot.http"),
            "http_request",
            method=request.method,
            path=request.url.path,
            http_status=http_status,
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
            error_type=error_type,
        )
        _session_id.reset(session_token)
        _request_id.reset(request_token)


def _redact(value: Any, key: str = "") -> Any:
    normalized = key.lower()
    if normalized in _SENSITIVE_KEYS or any(
        normalized.endswith(f"_{item}") for item in _SENSITIVE_KEYS
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
