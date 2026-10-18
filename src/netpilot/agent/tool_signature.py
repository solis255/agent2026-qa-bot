"""Canonical identities for validated Tool calls."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def canonical_tool_signature(
    tool_name: str, arguments: dict[str, Any], *, target_subject: str = "unknown",
    target_version: int = 1, execution_scope: str | None = None,
) -> str:
    """Return subject/version + tool_name + canonical JSON for validated calls.

    Pydantic input models supply defaults before this function is called.  The
    remaining normalization makes semantically identical hosts, URLs and RAG
    queries stable across model turns.
    """

    name = tool_name.strip().lower()
    normalized = _normalize_arguments(name, arguments)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    namespace = "target_neutral:v1" if execution_scope == "target_neutral" or name == "knowledge_search" else f"{target_subject}:v{target_version}"
    return f"{namespace}:{name}:{payload}"


def _normalize_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_value(arguments)
    if not isinstance(normalized, dict):
        return {}
    for field in ("host", "domain"):
        value = normalized.get(field)
        if isinstance(value, str):
            normalized[field] = value.strip().lower().rstrip(".")
    if tool_name == "http_check" and isinstance(normalized.get("url"), str):
        normalized["url"] = _canonical_url(normalized["url"])
    if tool_name == "knowledge_search" and isinstance(normalized.get("query"), str):
        normalized["query"] = " ".join(normalized["query"].split()).casefold()
    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    return value


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port
    if (scheme, port) in {("http", 80), ("https", 443)}:
        port = None
    netloc_host = f"[{host}]" if ":" in host else host
    netloc = f"{netloc_host}:{port}" if port is not None else netloc_host
    return urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
