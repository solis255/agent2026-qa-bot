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
        retry_after_seconds: float | None = None,
        provider_error_code: str | None = None,
        attempts_made: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id
        self.retry_after_seconds = retry_after_seconds
        self.provider_error_code = provider_error_code
        self.attempts_made = attempts_made


class LLMNotConfiguredError(TJUClientError):
    code = "llm_not_configured"


class LLMRequestError(TJUClientError):
    code = "llm_invalid_request"


class LLMAuthenticationError(TJUClientError):
    code = "llm_authentication_failed"


class LLMRateLimitError(TJUClientError):
    code = "llm_rate_limited"

    def __init__(self, message: str, *, quota_exhausted: bool = False, **metadata) -> None:
        super().__init__(message, **metadata)
        self.quota_exhausted = quota_exhausted


class LLMTimeoutError(TJUClientError):
    code = "llm_timeout"


class LLMConnectionError(TJUClientError):
    code = "llm_connection_failed"


class LLMServiceError(TJUClientError):
    code = "llm_service_error"


class LLMResponseError(TJUClientError):
    code = "llm_invalid_response"
