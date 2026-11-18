"""Exercise the actual OpenAI SDK against an offline HTTP transport."""
from functools import partial
import json
import logging

import httpx
import pytest
from openai import DefaultHttpxClient

from netpilot.llm import LLMAuthenticationError, LLMRateLimitError, LLMRequestError, TJUClient
from netpilot.llm import tju_client
from test_netpilot_llm import make_settings, messages


def completion(content="有依据的知识回答。"):
    return {"id": "offline", "object": "chat.completion", "created": 1, "model": "tju-llm",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}]}


def use_mock_transport(monkeypatch, respond):
    waits = []
    monkeypatch.setattr(tju_client, "sleep", waits.append)
    monkeypatch.setattr(tju_client, "random", lambda: 0.0)
    monkeypatch.setattr(tju_client, "DefaultHttpxClient", partial(
        DefaultHttpxClient, transport=httpx.MockTransport(respond),
    ))
    return waits


def error_response(status, headers=None, *, code=None, kind=None, attempt=1):
    return httpx.Response(status, headers={"x-request-id": f"upstream-{attempt}", **(headers or {})},
                          json={"error": {"message": "PRIVATE_BODY unit-test-secret", "code": code, "type": kind}})


def collect_attempts(caplog):
    return [json.loads(record.message) for record in caplog.records
            if record.name == "netpilot.llm.tju_client"]


@pytest.fixture
def scripted(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="netpilot.llm.tju_client")

    def run(responses, *, max_retries=2):
        requests = []
        remaining = iter(responses)

        def respond(req):
            requests.append(req)
            return next(remaining)

        waits = use_mock_transport(monkeypatch, respond)
        client = TJUClient(make_settings(tju_max_retries=max_retries))
        try:
            assert client._client.max_retries == 0
            try:
                result = client.chat(messages())
            except (LLMRateLimitError, LLMRequestError, LLMAuthenticationError) as exc:
                result = exc
        finally:
            client.close()
        return result, len(requests), waits, collect_attempts(caplog)
    return run


@pytest.mark.parametrize("count", [1, 2])
def test_transient_429_recovers_with_one_retry_layer(scripted, count):
    result, total, waits, logs = scripted([error_response(429)] * count + [httpx.Response(200, json=completion())])
    assert total == result.attempts_made == count + 1
    assert result.retry_count == count
    assert result.content == completion()["choices"][0]["message"]["content"]
    assert waits == [0.5, 1.0][:count]
    assert [item["will_retry"] for item in logs] == [True] * count + [False]
    assert [item["attempt"] for item in logs] == list(range(1, count + 2))
    assert all(item["provider_reason"] == "unknown_429" for item in logs[:-1])


def test_continuous_429_keeps_only_safe_metadata(scripted, caplog):
    exc, total, waits, logs = scripted([
        error_response(429, {"retry-after": "1.5"}, code="service_busy", attempt=i) for i in range(1, 4)
    ])
    assert total == exc.attempts_made == 3
    assert exc.status_code == 429 and exc.request_id == "upstream-3"
    assert exc.retry_after_seconds == 1.5 and exc.provider_error_code == "service_busy"
    assert exc.__cause__ is None and exc.__context__ is None
    assert waits == [1.5, 1.5]
    assert logs[-1]["retry_stop_reason"] == "attempt_limit"
    assert logs[-1]["provider_request_id"] == "upstream-3"
    assert "PRIVATE_BODY" not in caplog.text and "unit-test-secret" not in caplog.text


@pytest.mark.parametrize(("headers", "wait"), [
    ({"retry-after": "1.25", "retry-after-ms": "200"}, 1.25),
    ({"retry-after-ms": "375"}, 0.375),
    ({"retry-after": "0"}, 0),
    ({"retry-after": "Thu, 01 Jan 1970 00:00:00 GMT"}, 0),
    ({"retry-after": "NaN", "retry-after-ms": "-40"}, 0.5),
    ({"retry-after-ms": "inf"}, 0.5),
])
def test_retry_after_supported_formats_and_invalid_values(scripted, headers, wait):
    _, total, waits, logs = scripted([error_response(429, headers), httpx.Response(200, json=completion())])
    assert total == 2 and waits == [wait]
    assert logs[0]["retry_delay_seconds"] == wait


@pytest.mark.parametrize("first_delay", [11, 6])
def test_wait_budget_never_sleeps_early_or_past_budget(scripted, first_delay):
    exc, total, waits, logs = scripted([error_response(429, {"retry-after": str(first_delay)})] * 3)
    assert total == (1 if first_delay == 11 else 2)
    assert waits == ([] if first_delay == 11 else [6])
    assert exc.retry_after_seconds == first_delay and exc.status_code == 429
    assert logs[-1]["retry_stop_reason"] == "wait_budget"


def test_zero_retries_makes_one_request(scripted):
    exc, total, waits, logs = scripted([error_response(429)], max_retries=0)
    assert total == exc.attempts_made == 1 and waits == []
    assert logs[-1]["retry_stop_reason"] == "attempt_limit"


@pytest.mark.parametrize(("status", "type_"), [(400, LLMRequestError), (401, LLMAuthenticationError), (403, LLMAuthenticationError)])
def test_nonretryable_http_errors_ignore_even_an_explicit_retry_header(scripted, status, type_):
    exc, total, waits, _ = scripted([error_response(status, {"x-should-retry": "true"})])
    assert isinstance(exc, type_) and exc.status_code == status
    assert total == 1 and not waits


@pytest.mark.parametrize(("code", "kind"), [
    ("insufficient_quota", None), ("quota_exceeded", None), ("billing_hard_limit", None),
    ("daily_quota_exceeded", None), ("unknown_code", "insufficient_quota"),
])
def test_only_explicit_quota_codes_stop_without_retry(scripted, code, kind):
    exc, total, waits, logs = scripted([error_response(429, {"retry-after": "1"}, code=code, kind=kind)])
    assert total == 1 and waits == [] and not exc.retryable
    assert exc.quota_exhausted and exc.status_code == 429 and exc.provider_error_code == (code or kind)
    assert exc.provider_error_type == kind
    assert logs[0]["provider_reason"] == "quota_exhausted"


def test_untrusted_metadata_removed_and_provider_opt_out_honored(scripted, caplog):
    headers = {"x-request-id": "unit-test-secret", "x-should-retry": "false"}
    exc, total, waits, logs = scripted([error_response(429, headers, code="unit-test-secret", kind="a" * 49)])
    assert total == 1 and not waits and not exc.quota_exhausted
    assert exc.request_id is None and exc.provider_error_code is None
    assert logs[-1]["retry_stop_reason"] == "not_retryable"
    assert "unit-test-secret" not in caplog.text


@pytest.mark.parametrize("transport_error", [httpx.ConnectError, httpx.ReadTimeout])
def test_existing_transport_retry_types_are_bounded(monkeypatch, transport_error):
    count = 0

    def respond(request):
        nonlocal count
        count += 1
        if count <= 2:
            raise transport_error("private", request=request)
        return httpx.Response(200, json=completion())

    waits = use_mock_transport(monkeypatch, respond)
    client = TJUClient(make_settings())
    try:
        assert client.chat(messages()).attempts_made == count == 3
        assert waits == [0.5, 1.0]
    finally:
        client.close()
