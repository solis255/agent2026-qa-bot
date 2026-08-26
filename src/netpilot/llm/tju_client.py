"""Production TJU OpenAI-compatible chat and Function Calling client."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

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
    FunctionCall,
    TokenUsage,
    ToolCall,
)


ClientFactory = Callable[..., Any]


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
                max_retries=settings.tju_max_retries,
            )

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

        request_messages = [message.to_api_dict() for message in messages]
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
        started = perf_counter()
        try:
            response = self._client.chat.completions.create(**request)
        except AuthenticationError as exc:
            raise LLMAuthenticationError(
                "TJU API 认证失败（401），请检查 TJU_API_KEY。",
                status_code=401,
                request_id=_request_id(exc),
            ) from exc
        except RateLimitError as exc:
            raise LLMRateLimitError(
                "TJU API 请求过于频繁（429），有限重试后仍未成功。",
                retryable=True,
                status_code=429,
                request_id=_request_id(exc),
            ) from exc
        except APITimeoutError as exc:
            raise LLMTimeoutError(
                "TJU API 请求超时。",
                retryable=True,
                request_id=_request_id(exc),
            ) from exc
        except APIConnectionError as exc:
            raise LLMConnectionError(
                "无法连接 TJU API，请检查网络和专属地址。",
                retryable=True,
                request_id=_request_id(exc),
            ) from exc
        except APIResponseValidationError as exc:
            raise LLMResponseError(
                "TJU API 返回了无法解析的响应。",
                status_code=_status_code(exc),
                request_id=_request_id(exc),
            ) from exc
        except APIStatusError as exc:
            status_code = _status_code(exc)
            raise LLMServiceError(
                _safe_status_message(status_code),
                retryable=status_code is None or status_code >= 500,
                status_code=status_code,
                request_id=_request_id(exc),
            ) from exc
        except APIError as exc:
            raise LLMResponseError(
                "TJU API 返回了无法处理的响应。",
                request_id=_request_id(exc),
            ) from exc

        duration_ms = (perf_counter() - started) * 1000
        return _parse_response(response, self.model, duration_ms)


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


def _request_id(exc: Exception) -> str | None:
    value = getattr(exc, "request_id", None)
    return value if isinstance(value, str) and value else None


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "status_code", None)
    return value if isinstance(value, int) else None


def _safe_status_message(status_code: int | None) -> str:
    if status_code is None:
        return "TJU API 返回了服务错误。"
    return f"TJU API 返回 HTTP {status_code}。"
