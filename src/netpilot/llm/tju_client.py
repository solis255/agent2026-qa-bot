"""Production TJU OpenAI-compatible chat and Function Calling client."""

from __future__ import annotations

from collections.abc import Callable, Sequence
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
_CODE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,47}", re.ASCII)
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", re.ASCII)


class TJUClient:
    """Thin, testable boundary around the TJU Chat Completions endpoint."""

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
            assert settings.tju_api_key is not None
            self._client = client_factory(
                api_key=settings.tju_api_key.get_secret_value().strip(),
                base_url=settings.tju_api_base,
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
        return self._settings.tju_model

    def __repr__(self) -> str:
        return f"TJUClient(configured={self.configured!r}, model={self.model!r})"

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
                "TJU LLM 未配置，请在项目根目录 .env 中设置 TJU_API_KEY。"
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
        return self._complete(request)

    def _complete(self, request: dict[str, Any]) -> ChatResult:
        started = perf_counter()
        budget = _RETRY_WAIT_BUDGET
        max_retries = self._settings.tju_max_retries
        api_key = self._settings.tju_api_key
        assert api_key is not None
        secret = api_key.get_secret_value().strip()
        for attempt in range(1, max_retries + 2):
            attempt_started = perf_counter()
            headers = Headers()
            try:
                response = self._client.chat.completions.create(**request)
                result = _parse_response(response, self.model, (perf_counter() - started) * 1000)
            except APIError as exc:
                if isinstance(exc, (APIStatusError, APIResponseValidationError)):
                    headers = exc.response.headers
                error = _map_sdk_error(exc, headers, secret, attempt)
            except LLMResponseError as exc:
                error = LLMResponseError(str(exc), status_code=200, attempts_made=attempt,
                                         request_id=_safe_metadata(getattr(response, "_request_id", None), _ID_PATTERN, secret))
            else:
                request_id = _safe_metadata(result.request_id, _ID_PATTERN, secret)
                log_event(logger, "tju_llm_request", success=True, status_code=200, attempt=attempt,
                          max_retries=max_retries, provider_request_id=request_id, model=self.model,
                          will_retry=False, duration_ms=round((perf_counter() - attempt_started) * 1000))
                return result.model_copy(update={"attempts_made": attempt, "request_id": request_id})

            delay, stop_reason = _retry_decision(error, headers, attempt, max_retries, budget)
            rate_limit = isinstance(error, LLMRateLimitError)
            log_event(logger, "tju_llm_request", success=False, status_code=error.status_code,
                      error_type=type(error).__name__, provider_error_code=error.provider_error_code,
                      provider_request_id=error.request_id, model=self.model, attempt=attempt,
                      max_retries=max_retries, retry_after_seconds=error.retry_after_seconds,
                      will_retry=delay is not None, retry_delay_seconds=delay, retry_stop_reason=stop_reason,
                      provider_reason=("quota_exhausted" if error.quota_exhausted else "unknown_429") if rate_limit else None,
                      duration_ms=round((perf_counter() - attempt_started) * 1000))
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
    status = _status_code(exc)
    code = _safe_metadata(getattr(exc, "code", None), _CODE_PATTERN, secret)
    kind = _safe_metadata(getattr(exc, "type", None), _CODE_PATTERN, secret)
    code = code or kind
    quota_code = next((value for value in (code, kind) if value and value.lower() in _QUOTA_CODES), None)
    metadata = {
        "status_code": status,
        "request_id": _safe_metadata(getattr(exc, "request_id", None), _ID_PATTERN, secret),
        "retry_after_seconds": _retry_after(headers),
        "provider_error_code": code,
        "attempts_made": attempt,
    }
    if status == 429 and isinstance(exc, APIStatusError):
        if quota_code:
            metadata["provider_error_code"] = quota_code
            return LLMRateLimitError("TJU 模型 API 的可用配额可能已耗尽。", quota_exhausted=True, **metadata)
        return LLMRateLimitError("TJU API 暂时限流（429），请稍后重试。", retryable=True, **metadata)
    if isinstance(exc, BadRequestError) or status == 400:
        return LLMRequestError("TJU API 拒绝请求（400），请检查请求参数。", **metadata)
    if isinstance(exc, AuthenticationError) or status == 401:
        return LLMAuthenticationError("TJU API 认证失败（401），请检查 TJU_API_KEY。", **metadata)
    if isinstance(exc, PermissionDeniedError) or status == 403:
        return LLMAuthenticationError("TJU API 拒绝访问（403），请检查项目权限。", **metadata)
    if isinstance(exc, APITimeoutError):
        return LLMTimeoutError("TJU API 请求超时。", retryable=True, **metadata)
    if isinstance(exc, APIConnectionError):
        return LLMConnectionError("无法连接 TJU API，请检查网络和专属地址。", retryable=True, **metadata)
    if isinstance(exc, APIResponseValidationError):
        return LLMResponseError("TJU API 返回了无法解析的响应。", **metadata)
    if isinstance(exc, APIStatusError):
        return LLMServiceError(_safe_status_message(status),
                               retryable=status in {408, 409} or (status is not None and status >= 500),
                               **metadata)
    return LLMResponseError("TJU API 返回了无法处理的响应。", **metadata)


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


def _parse_response(response: Any, configured_model: str, duration_ms: float) -> ChatResult:
    """Validate the small response subset used by ordinary chat."""

    try:
        choices = response.choices
        if not choices:
            raise ValueError("missing choices")
        choice = choices[0]
        raw_content = getattr(choice.message, "content", None)
        content = raw_content.strip() if isinstance(raw_content, str) else None
        content = content or None
        tool_calls = _parse_tool_calls(getattr(choice.message, "tool_calls", None))
        if content is None and not tool_calls:
            raise ValueError("missing message content and tool calls")

        response_model = getattr(response, "model", None) or configured_model
        if not isinstance(response_model, str) or not response_model.strip():
            raise ValueError("invalid model")

        usage = getattr(response, "usage", None)
        token_usage = TokenUsage(
            prompt_tokens=_token_count(usage, "prompt_tokens"),
            completion_tokens=_token_count(usage, "completion_tokens"),
            total_tokens=_token_count(usage, "total_tokens"),
        )
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason is not None and not isinstance(finish_reason, str):
            finish_reason = str(finish_reason)

        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            model=response_model.strip(),
            finish_reason=finish_reason,
            usage=token_usage,
            request_id=getattr(response, "_request_id", None),
            duration_ms=duration_ms,
        )
    except TJUClientError:
        raise
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        raise LLMResponseError("TJU API 返回了不完整或异常的响应。") from exc


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    if raw_tool_calls is None:
        return []
    if not isinstance(raw_tool_calls, (list, tuple)):
        raise ValueError("tool_calls must be a list")

    parsed: list[ToolCall] = []
    for raw_call in raw_tool_calls:
        function = raw_call.function
        parsed.append(
            ToolCall(
                id=raw_call.id,
                type=raw_call.type,
                function=FunctionCall(
                    name=function.name,
                    arguments=function.arguments,
                ),
            )
        )
    return parsed


def _token_count(usage: Any, field: str) -> int:
    value = getattr(usage, field, 0) if usage is not None else 0
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
        return "TJU API 返回了服务错误。"
    return f"TJU API 返回 HTTP {status_code}。"
