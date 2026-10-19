import json
import logging
from netpilot.observability import log_event
from netpilot.privacy.logging import safe_log_context
from netpilot.privacy import safe_value


def test_logs_drop_all_payloads_even_unknown_keys_and_nested_arguments(caplog):
    logger = logging.getLogger("netpilot.privacy-test")
    with caplog.at_level(logging.INFO, logger="netpilot"):
        log_event(logger, "tool_execution", session_id="internal-id", tool_name="dns_lookup",
            Authorization="Bearer auth-secret", cookie="cookie-secret", raw_snapshot={"x": "raw-secret"},
            arguments={"api_key": "key-secret"}, unexpected_payload="unlabelled-secret")
    assert all(secret not in caplog.text for secret in ["auth-secret", "cookie-secret", "raw-secret", "key-secret", "unlabelled-secret"])
    payload = json.loads(caplog.records[-1].getMessage())
    assert payload["session_id"] == "internal-id" and payload["tool_name"] == "dns_lookup"
    assert "arguments" not in payload
    assert safe_log_context({"body": "opaque"}) == {}


def test_audit_contains_only_categories_and_count(caplog):
    with caplog.at_level(logging.INFO, logger="netpilot"):
        safe_value({"password": "audit-secret", "summary": "token=note-secret"}, context="persistence")
    assert "audit-secret" not in caplog.text and "note-secret" not in caplog.text
    event = json.loads(caplog.records[-1].getMessage())
    assert event["event"] == "redaction_applied"
    assert event["categories"] == ["credential"] and event["count"] == 2
