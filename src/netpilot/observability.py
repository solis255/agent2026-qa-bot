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
from netpilot.privacy.logging import safe_log_context


_request_id: ContextVar[str] = ContextVar("netpilot_request_id", default="-")
_session_id: ContextVar[str] = ContextVar("netpilot_session_id", default="-")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


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
        json.dumps(safe_log_context(payload), ensure_ascii=False, separators=(",", ":")),
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
            path=_log_route(request),
            http_status=http_status,
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
            error_type=error_type,
        )
        _session_id.reset(session_token)
        _request_id.reset(request_token)


def _log_route(request: Request) -> str:
    path = getattr(request.scope.get("route"), "path", None)
    if path is None:
        return "[unmatched_route]"
    # New FastAPI route scopes may store the path relative to an API router.
    return "/api" + path if request.url.path.startswith("/api/") and not path.startswith("/api/") else path


def _redact(value: Any, key: str = "") -> Any:
    from netpilot.privacy import redact_mapping
    return redact_mapping({key: value}).value[key]
