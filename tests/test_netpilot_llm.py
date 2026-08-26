from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    RateLimitError,
)

from netpilot.config import Settings
from netpilot.llm import (
    ChatMessage,
    FunctionCall,
    LLMAuthenticationError,
    LLMConnectionError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    TJUClient,
    ToolCall,
)


class FakeCompletions:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeSDKClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.completions = FakeCompletions(response=response, error=error)
        self.chat = SimpleNamespace(completions=self.completions)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "tju_api_key": "unit-test-secret",
        "tju_api_base": "https://ai.tju.edu.cn/api/agent2026/unit-test",
    }
    values.update(overrides)
    return Settings(**values)


def make_response(
    *,
    content: Any = "诊断建议",
    choices: list[Any] | None = None,
    usage: Any = None,
) -> Any:
    if choices is None:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ]
    if usage is None:
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=4,
            total_tokens=14,
        )
    return SimpleNamespace(
        choices=choices,
        model="tju-llm",
        usage=usage,
        _request_id="req_test_123",
    )


def messages() -> list[ChatMessage]:
    return [
        ChatMessage(role="system", content="你是校园网络助手。"),
        ChatMessage(role="user", content="为什么无法解析域名？"),
    ]


def test_unconfigured_client_does_not_construct_the_sdk() -> None:
    constructed = False

    def factory(**_kwargs: Any) -> Any:
        nonlocal constructed
        constructed = True
        return FakeSDKClient(make_response())

    client = TJUClient(
        Settings(_env_file=None, tju_api_key=None),
        client_factory=factory,
    )

    assert client.configured is False
    assert constructed is False
    with pytest.raises(LLMNotConfiguredError, match="未配置"):
        client.chat(messages())


def test_client_factory_receives_bounded_sdk_configuration() -> None:
    captured: dict[str, Any] = {}
    fake = FakeSDKClient(make_response())

    def factory(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return fake

    settings = make_settings(tju_timeout_seconds=45, tju_max_retries=3)
    client = TJUClient(settings, client_factory=factory)

    assert captured == {
        "api_key": "unit-test-secret",
        "base_url": "https://ai.tju.edu.cn/api/agent2026/unit-test",
        "timeout": 45.0,
        "max_retries": 3,
    }
    assert "unit-test-secret" not in repr(client)


def test_chat_sends_an_ordinary_non_streaming_completion() -> None:
    fake = FakeSDKClient(make_response())
    client = TJUClient(make_settings(), sdk_client=fake)

    result = client.chat(messages(), temperature=0.1, max_tokens=256)

    assert fake.completions.calls == [
        {
            "model": "tju-llm",
            "messages": [
                {"role": "system", "content": "你是校园网络助手。"},
                {"role": "user", "content": "为什么无法解析域名？"},
            ],
            "temperature": 0.1,
            "max_tokens": 256,
            "stream": False,
        }
    ]
    assert result.content == "诊断建议"
    assert result.model == "tju-llm"
    assert result.finish_reason == "stop"
    assert result.usage.model_dump() == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
    }
    assert result.request_id == "req_test_123"
    assert result.duration_ms >= 0


def test_chat_allows_a_response_without_usage() -> None:
    response = make_response()
    response.usage = None
    client = TJUClient(make_settings(), sdk_client=FakeSDKClient(response))

    result = client.chat(messages())

    assert result.usage.total_tokens == 0


def test_chat_sends_tools_and_parses_native_function_calls() -> None:
    raw_tool_call = SimpleNamespace(
        id="call_dns_1",
        type="function",
        function=SimpleNamespace(
            name="dns_lookup",
            arguments='{"domain":"github.com"}',
        ),
    )
    response = make_response(content=None)
    response.choices[0].message.tool_calls = [raw_tool_call]
    fake = FakeSDKClient(response)
    client = TJUClient(make_settings(), sdk_client=fake)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "dns_lookup",
                "parameters": {"type": "object"},
            },
        }
    ]

    result = client.chat(messages(), tools=tools, tool_choice="auto")

    assert fake.completions.calls[0]["tools"] == tools
    assert fake.completions.calls[0]["tool_choice"] == "auto"
    assert result.content is None
    assert result.tool_calls == [
        ToolCall(
            id="call_dns_1",
            function=FunctionCall(
                name="dns_lookup",
                arguments='{"domain":"github.com"}',
            ),
        )
    ]
    serialized_call = result.to_assistant_message().to_api_dict()["tool_calls"][0]
    assert serialized_call["id"] == "call_dns_1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"messages": []},
        {"messages": messages(), "temperature": -0.1},
        {"messages": messages(), "temperature": 2.1},
        {"messages": messages(), "max_tokens": 0},
    ],
)
def test_chat_rejects_invalid_local_requests(kwargs: dict[str, Any]) -> None:
    client = TJUClient(make_settings(), sdk_client=FakeSDKClient(make_response()))

    with pytest.raises(LLMRequestError):
        client.chat(**kwargs)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.invalid/chat/completions")


def _status_exception(error_type: type[Exception], status: int, message: str) -> Exception:
    response = httpx.Response(
        status,
        request=_request(),
        headers={"x-request-id": f"req_{status}"},
    )
    return error_type(message, response=response, body=None)


@pytest.mark.parametrize(
    ("sdk_error", "expected_type", "status_code", "retryable"),
    [
        (
            _status_exception(
                AuthenticationError,
                401,
                "server included unit-test-secret in its message",
            ),
            LLMAuthenticationError,
            401,
            False,
        ),
        (
            _status_exception(RateLimitError, 429, "rate limited"),
            LLMRateLimitError,
            429,
            True,
        ),
        (
            APITimeoutError(_request()),
            LLMTimeoutError,
            None,
            True,
        ),
        (
            APIConnectionError(request=_request()),
            LLMConnectionError,
            None,
            True,
        ),
        (
            _status_exception(InternalServerError, 500, "server failed"),
            LLMServiceError,
            500,
            True,
        ),
    ],
)
def test_sdk_errors_are_wrapped_safely(
    sdk_error: Exception,
    expected_type: type[Exception],
    status_code: int | None,
    retryable: bool,
) -> None:
    client = TJUClient(make_settings(), sdk_client=FakeSDKClient(error=sdk_error))

    with pytest.raises(expected_type) as captured:
        client.chat(messages())

    assert captured.value.status_code == status_code
    assert captured.value.retryable is retryable
    assert "unit-test-secret" not in str(captured.value)
    assert "unit-test-secret" not in repr(captured.value)


def test_sdk_response_validation_error_is_wrapped() -> None:
    response = httpx.Response(200, request=_request())
    sdk_error = APIResponseValidationError(response=response, body="not-json")
    client = TJUClient(make_settings(), sdk_client=FakeSDKClient(error=sdk_error))

    with pytest.raises(LLMResponseError, match="无法解析"):
        client.chat(messages())


def test_generic_sdk_parse_error_is_wrapped_without_leaking_details() -> None:
    sdk_error = APIError(
        "invalid response containing unit-test-secret",
        _request(),
        body="not-json",
    )
    client = TJUClient(make_settings(), sdk_client=FakeSDKClient(error=sdk_error))

    with pytest.raises(LLMResponseError) as captured:
        client.chat(messages())

    assert "unit-test-secret" not in str(captured.value)


@pytest.mark.parametrize(
    "response",
    [
        make_response(choices=[]),
        make_response(content=None),
        make_response(content="   "),
        SimpleNamespace(choices=[SimpleNamespace(message=None)]),
    ],
)
def test_malformed_chat_responses_are_rejected(response: Any) -> None:
    client = TJUClient(make_settings(), sdk_client=FakeSDKClient(response))

    with pytest.raises(LLMResponseError, match="不完整或异常"):
        client.chat(messages())


def test_malformed_native_tool_call_is_rejected() -> None:
    response = make_response(content=None)
    response.choices[0].message.tool_calls = [
        SimpleNamespace(
            id="",
            type="function",
            function=SimpleNamespace(name="dns_lookup", arguments="{}"),
        )
    ]
    client = TJUClient(make_settings(), sdk_client=FakeSDKClient(response))

    with pytest.raises(LLMResponseError, match="不完整或异常"):
        client.chat(messages(), tools=[{"type": "function", "function": {}}])


def test_injected_mock_client_is_not_closed_by_the_wrapper() -> None:
    fake = FakeSDKClient(make_response())
    client = TJUClient(make_settings(), sdk_client=fake)

    client.close()

    assert fake.closed is False
