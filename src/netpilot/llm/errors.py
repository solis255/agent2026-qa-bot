"""Safe, stable errors exposed by the NetPilot TJU client."""

from __future__ import annotations


class TJUClientError(RuntimeError):
    """Base error that contains only user-safe operational metadata."""

    code = "llm_error"

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id


class LLMNotConfiguredError(TJUClientError):
    code = "llm_not_configured"


class LLMRequestError(TJUClientError):
    code = "llm_invalid_request"


class LLMAuthenticationError(TJUClientError):
    code = "llm_authentication_failed"


class LLMRateLimitError(TJUClientError):
    code = "llm_rate_limited"


class LLMTimeoutError(TJUClientError):
    code = "llm_timeout"


class LLMConnectionError(TJUClientError):
    code = "llm_connection_failed"


class LLMServiceError(TJUClientError):
    code = "llm_service_error"


class LLMResponseError(TJUClientError):
    code = "llm_invalid_response"
