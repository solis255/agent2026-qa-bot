"""Log-safe means metadata only, never sanitized payload dumps."""
from .redactor import redact_mapping

LOG_FIELDS = frozenset({
    "event", "request_id", "session_id", "tool_name", "status", "duration", "duration_ms",
    "tool_duration", "tool_success", "error_type", "error_class", "success", "method", "path",
    "http_status", "llm_duration", "tool_rounds", "turn_intent", "response_mode", "fallback_reason",
    "rag_calls", "knowledge_finalization_attempts", "knowledge_finalization_failure_kind",
    "history_context_records", "categories", "count", "context", "event_type", "created_at",
    "attempt", "failure_kind", "finish_reason", "source_count", "policy_version",
    "has_content", "content_length", "has_tool_calls", "looks_like_textual_tool_call",
    "source_only_detected", "selected_chunk_count", "selected_context_chars", "llm_error_type",
    "knowledge_history_messages",
})


def safe_log_context(value=None, **fields):
    supplied = {**(value or {}), **fields}
    metadata = {key: item for key, item in supplied.items() if key in LOG_FIELDS
                and (item is None or isinstance(item, (str, int, float, bool))
                     or key == "categories" and isinstance(item, list))}
    return redact_mapping(metadata).value


def audit(result, context):
    if not result.changed: return
    import logging
    from netpilot.observability import log_event
    log_event(logging.getLogger("netpilot.privacy"), "redaction_applied",
              categories=result.redacted_categories, count=result.redacted_count, context=context)
