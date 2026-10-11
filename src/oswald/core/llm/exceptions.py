"""LLM exception hierarchy.

Provides flattened exceptions for provider errors and rate limits.
Agent implementations and pipeline runners catch these unified types
rather than vendor-specific exception classes.
"""


class LLMError(Exception):
    """Base exception for all LLM client failures."""

    def __init__(self, message: str, *, model: str = "") -> None:
        super().__init__(message)
        self.model = model


class LLMProviderError(LLMError):
    """Provider returned a server-side error (5xx, unexpected failure, or invalid auth)."""

    def __init__(
        self,
        message: str,
        *,
        model: str = "",
        status_code: int | None = None,
        is_retryable: bool = False,
    ) -> None:
        super().__init__(message, model=model)
        self.status_code = status_code
        self.is_retryable = is_retryable


class LLMRateLimitError(LLMError):
    """Provider rate limit or quota exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str,
        *,
        model: str = "",
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, model=model)
        self.retry_after_seconds = retry_after_seconds
