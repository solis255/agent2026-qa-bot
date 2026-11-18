"""OpenAI-compatible chat and Function Calling client."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import logging
import math
from random import random
import re
from time import perf_counter, sleep
from typing import Any

from httpx import Headers
from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    DefaultHttpxClient,
    BadRequestError,
    PermissionDeniedError,
    OpenAI,
)
from netpilot.observability import log_event

from netpilot.config import Settings
from netpilot.llm.errors import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMRequestError,
    LLMResponseError,
    LLMServiceError,
    LLMTimeoutError,
    TJUClientError,
)
from netpilot.llm.schemas import (
    ChatMessage,
    ChatResult,
    ChatRole,
    FunctionCall,
    TokenUsage,
    ToolCall,
)


ClientFactory = Callable[..., Any]
logger = logging.getLogger(__name__)
_RETRY_WAIT_BUDGET = 10.0  # Cumulative delay per completion; HTTP timeout remains per attempt.
_QUOTA_CODES = {"insufficient_quota", "quota_exceeded", "billing_hard_limit", "daily_quota_exceeded"}
_CODE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,47}", re.ASCII)
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", re.ASCII)
_MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}", re.ASCII)
_REQUEST_CODES = {"model_not_found", "invalid_model", "invalid_request", "invalid_request_error",
                  "context_length_exceeded", "unsupported_model", "invalid_parameter"}


class TJUClient:
    """Chat Completions client, retaining the public name for existing callers."""

    def __init__(
        self,
        settings: Settings,
        *,
        sdk_client: Any | None = None,
        client_factory: ClientFactory = OpenAI,
    ) -> None:
        self._settings = settings
        self._owns_client = sdk_client is None
        self._client = sdk_client

        if self._client is None and settings.llm_configured:
            api_key = settings.effective_llm_api_key
            assert api_key is not None
            self._client = client_factory(
                api_key=api_key.get_secret_value().strip(),
                base_url=settings.effective_llm_api_base,
                timeout=settings.tju_timeout_seconds,
                max_retries=0,
                http_client=DefaultHttpxClient(),
            )
        elif isinstance(self._client, OpenAI):
            self._client = self._client.with_options(max_retries=0)

    @property
    def configured(self) -> bool:
        """Return whether this instance can make a chat request."""

        return self._settings.llm_configured and self._client is not None

    @property
    def model(self) -> str:
        return self._settings.effective_llm_model or ""

    @property
    def provider(self) -> str:
        return self._settings.llm_provider

    @property
    def diagnostic_identity(self) -> dict[str, str | None]:
        key = self._settings.effective_llm_api_key
        secret = key.get_secret_value().strip() if key is not None else ""
        return {"provider": _safe_metadata(self.provider, _CODE_PATTERN, secret),
                "model": _safe_metadata(self.model, _MODEL_PATTERN, secret)}

    def __repr__(self) -> str:
        return f"TJUClient(configured={self.configured!r}, provider={self.diagnostic_identity['provider']!r})"

    def close(self) -> None:
        """Close the SDK transport owned by this wrapper."""

        if not self._owns_client or self._client is None:
            return
        client = self._client
        self._client = None
        close = getattr(client, "close", None)
        if callable(close):
            close()

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> ChatResult:
        """Send one non-streaming chat or native Function Calling request."""

        if not self.configured:
            raise LLMNotConfiguredError(
                "模型服务未配置，请检查 LLM_* 设置或旧版 TJU_* 设置。"
            )
        if not messages:
            raise LLMRequestError("聊天消息不能为空。")
        if not 0.0 <= temperature <= 2.0:
            raise LLMRequestError("temperature 必须在 0.0 到 2.0 之间。")
        if not 1 <= max_tokens <= 32_768:
            raise LLMRequestError("max_tokens 必须在 1 到 32768 之间。")
        if any(not isinstance(message, ChatMessage) for message in messages):
            raise LLMRequestError("messages 中的每一项都必须是 ChatMessage。")
        if tools is not None and not tools:
            raise LLMRequestError("tools 不能为空列表。")
        if tools is not None and tool_choice not in {"auto", "none", "required"}:
            raise LLMRequestError("tool_choice 必须是 auto、none 或 required。")

        system_prompts = []
        request_messages = []
        for message in messages:
            serialized = message.to_api_dict()
            if message.role is ChatRole.SYSTEM:
                system_prompts.append(serialized["content"])
            else:
                request_messages.append(serialized)
        # TJU's chat template accepts a single system message at the beginning.
        if system_prompts:
            request_messages.insert(0, {"role": "system", "content": "\n\n".join(system_prompts)})

        request: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools is not None:
            request["tools"] = list(tools)
            request["tool_choice"] = tool_choice
        if self.provider == "deepseek":
            request.pop("temperature")
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        return self._complete(request)

    def _complete(self, request: dict[str, Any]) -> ChatResult:
        started = perf_counter()
        budget = _RETRY_WAIT_BUDGET
        max_retries = self._settings.tju_max_retries
        api_key = self._settings.effective_llm_api_key
        assert api_key is not None
        secret = api_key.get_secret_value().strip()
        identity = self.diagnostic_identity
        for attempt in range(1, max_retries + 2):
            attempt_started = perf_counter()
            headers = Headers()
            status = 200
            request_id = None
            try:
                completions = self._client.chat.completions
                if isinstance(self._client, OpenAI):
                    raw = completions.with_raw_response.create(**request)
                    headers = raw.headers
                    status = raw.status_code
                    request_id = _provider_request_id(headers, secret)
                    response = raw.http_response.json()
                else:
                    response = completions.create(**request)
                    request_id = _safe_metadata(_field(response, "_request_id"), _ID_PATTERN, secret)
                envelope = _field(response, "error")
                if envelope is not None:
                    error = _map_error(status=status, code=_field(envelope, "code"),
                                       kind=_field(envelope, "type"), request_id=request_id,
                                       headers=headers, secret=secret, attempt=attempt)
                else:
                    result = _parse_response(response, self.model, (perf_counter() - started) * 1000)
            except APIError as exc:
                if isinstance(exc, (APIStatusError, APIResponseValidationError)):
                    headers = exc.response.headers
                error = _map_sdk_error(exc, headers, secret, attempt)
            except (LLMResponseError, ValueError):
                error = LLMResponseError("模型 API 返回了无法解析的响应。", status_code=status,
                                         attempts_made=attempt, request_id=request_id)
            else:
                if envelope is None:
                    safe_model = _safe_metadata(result.model, _MODEL_PATTERN, secret)
                    finish = _safe_metadata(result.finish_reason, _CODE_PATTERN, secret)
                    log_event(logger, "tju_llm_request", success=True, status_code=status, attempt=attempt,
                              max_retries=max_retries, provider_request_id=request_id,
                              will_retry=False, duration_ms=round((perf_counter() - attempt_started) * 1000),
                              **{**identity, "model": safe_model or identity["model"]})
                    return result.model_copy(update={"attempts_made": attempt, "request_id": request_id,
                                                     "model": safe_model or identity["model"] or "unknown",
                                                     "finish_reason": finish})

            delay, stop_reason = _retry_decision(error, headers, attempt, max_retries, budget)
            rate_limit = isinstance(error, LLMRateLimitError)
            log_event(logger, "tju_llm_request", success=False, status_code=error.status_code,
                      error_type=type(error).__name__, provider_error_code=error.provider_error_code,
                      provider_request_id=error.request_id, provider_error_type=error.provider_error_type,
                      attempt=attempt,
                      max_retries=max_retries, retry_after_seconds=error.retry_after_seconds,
                      will_retry=delay is not None, retry_delay_seconds=delay, retry_stop_reason=stop_reason,
                      provider_reason=("quota_exhausted" if error.quota_exhausted else "unknown_429") if rate_limit else None,
                      duration_ms=round((perf_counter() - attempt_started) * 1000), **identity)
            if delay is None:
                # Raised outside the SDK's except block: no underlying body/request in
                # the exception chain or in the public/logged error.
                raise error from None
            budget -= delay
            sleep(delay)
        raise AssertionError("retry loop must return or raise on its last attempt")


def _retry_after(headers: Headers) -> float | None:
    for header, scale in (("retry-after", 1.0), ("retry-after-ms", 0.001)):
        value = headers.get(header)
        if not value:
            continue
        try:
            delay = float(value) * scale
        except ValueError:
            if header != "retry-after":
                continue
            try:
                when = parsedate_to_datetime(value)
                delay = max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                continue
        if math.isfinite(delay) and delay >= 0:
            return delay
    return None


def _safe_metadata(value: Any, pattern: re.Pattern[str], secret: str) -> str | None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        return None
    lower = value.lower()
    if (secret and secret in value) or lower.startswith(("tk-", "sk-", "bearer", "token_", "api_key")):
        return None
    return value


def _map_sdk_error(exc: APIError, headers: Headers, secret: str, attempt: int) -> TJUClientError:
    return _map_error(status=_status_code(exc), code=getattr(exc, "code", None),
                      kind=getattr(exc, "type", None), request_id=getattr(exc, "request_id", None),
                      headers=headers, secret=secret, attempt=attempt, sdk_error=exc)


def _provider_request_id(headers: Headers, secret: str) -> str | None:
    return next((request_id for name in ("x-request-id", "request-id", "x-ds-request-id")
                 if (request_id := _safe_metadata(headers.get(name), _ID_PATTERN, secret))), None)


def _map_error(*, status, code, kind, request_id, headers, secret, attempt, sdk_error=None) -> TJUClientError:
    code = _safe_metadata(code, _CODE_PATTERN, secret)
    kind = _safe_metadata(kind, _CODE_PATTERN, secret)
    tags = {value.lower() for value in (code, kind) if value}
    metadata = {
        "status_code": status,
        "request_id": _safe_metadata(request_id, _ID_PATTERN, secret) or _provider_request_id(headers, secret),
        "retry_after_seconds": _retry_after(headers),
        "provider_error_code": code,
        "provider_error_type": kind,
        "attempts_made": attempt,
    }
    if status == 429 and isinstance(sdk_error, APIStatusError):
        if tags & _QUOTA_CODES:
            metadata["provider_error_code"] = code or kind
            return LLMRateLimitError("模型 API 的可用配额可能已耗尽。", quota_exhausted=True, **metadata)
        return LLMRateLimitError("模型 API 暂时限流（429），请稍后重试。", retryable=True, **metadata)
    if status == 401 or isinstance(sdk_error, AuthenticationError):
        return LLMAuthenticationError("模型 API 认证失败（401），请检查 API Key。", **metadata)
    if status == 403 or isinstance(sdk_error, PermissionDeniedError):
        return LLMAuthenticationError("模型 API 拒绝访问（403），请检查项目权限。", **metadata)
    if status == 400 or isinstance(sdk_error, BadRequestError) or (
        status in {200, 404, 422} and tags & _REQUEST_CODES
    ):
        return LLMRequestError("模型 API 拒绝请求，请检查模型名称和请求参数。", **metadata)
    if isinstance(sdk_error, APITimeoutError):
        return LLMTimeoutError("模型 API 请求超时。", retryable=True, **metadata)
    if isinstance(sdk_error, APIConnectionError):
        return LLMConnectionError("无法连接模型 API，请检查网络和服务地址。", retryable=True, **metadata)
    if sdk_error is None:
        return LLMServiceError("模型 API 返回了服务错误。", **metadata)
    if isinstance(sdk_error, APIStatusError):
        return LLMServiceError(_safe_status_message(status),
                               retryable=status in {408, 409} or (status is not None and status >= 500),
                               **metadata)
    return LLMResponseError("模型 API 返回了无法解析的响应。", **metadata)


def _retry_decision(
    error: TJUClientError, headers: Headers, attempt: int, max_retries: int, budget: float,
) -> tuple[float | None, str | None]:
    if isinstance(error, LLMRateLimitError) and error.quota_exhausted:
        return None, "quota_exhausted"
    if not error.retryable or headers.get("x-should-retry", "").lower() == "false":
        return None, "not_retryable"
    if attempt > max_retries:
        return None, "attempt_limit"
    delay = error.retry_after_seconds
    if delay is None:
        delay = min(0.5 * 2 ** (attempt - 1), 4.0) * (1.0 - 0.25 * random())
    if delay > budget:
        return None, "wait_budget"
    return delay, None


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _parse_response(response: Any, configured_model: str, duration_ms: float) -> ChatResult:
    """Validate the small response subset used by ordinary chat."""

    try:
        choices = _field(response, "choices")
        if not isinstance(choices, (list, tuple)) or not choices:
            raise ValueError("missing choices")
        choice = choices[0]
        message = _field(choice, "message")
        if message is None:
            raise ValueError("missing message")
        raw_content = _field(message, "content")
        if raw_content is not None and not isinstance(raw_content, str):
            raise ValueError("invalid message content")
        content = raw_content.strip() if isinstance(raw_content, str) else None
        content = content or None
        tool_calls = _parse_tool_calls(_field(message, "tool_calls"))
        reasoning = _field(message, "reasoning_content")

        response_model = _field(response, "model") or configured_model
        if not isinstance(response_model, str) or not response_model.strip():
            raise ValueError("invalid model")

        usage = _field(response, "usage")
        token_usage = TokenUsage(
            prompt_tokens=_token_count(usage, "prompt_tokens"),
            completion_tokens=_token_count(usage, "completion_tokens"),
            total_tokens=_token_count(usage, "total_tokens"),
        )
        finish_reason = _field(choice, "finish_reason")

        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            model=response_model.strip(),
            finish_reason=finish_reason,
            has_reasoning_content=isinstance(reasoning, str) and bool(reasoning.strip()),
            usage=token_usage,
            duration_ms=duration_ms,
        )
    except TJUClientError:
        raise
    except (AttributeError, IndexError, TypeError, ValueError):
        raise LLMResponseError("模型 API 返回了不完整或异常的响应。") from None


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    if raw_tool_calls is None:
        return []
    if not isinstance(raw_tool_calls, (list, tuple)):
        raise ValueError("tool_calls must be a list")

    parsed: list[ToolCall] = []
    for raw_call in raw_tool_calls:
        function = _field(raw_call, "function")
        parsed.append(
            ToolCall(
                id=_field(raw_call, "id"),
                type=_field(raw_call, "type"),
                function=FunctionCall(
                    name=_field(function, "name"),
                    arguments=_field(function, "arguments"),
                ),
            )
        )
    return parsed


def _token_count(usage: Any, field: str) -> int:
    value = _field(usage, field, 0)
    if value is None:
        return 0
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid usage field: {field}")
    return value


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    return value if isinstance(value, int) else None


def _safe_status_message(status_code: int | None) -> str:
    if status_code is None:
        return "模型 API 返回了服务错误。"
    return f"模型 API 返回 HTTP {status_code}。"
