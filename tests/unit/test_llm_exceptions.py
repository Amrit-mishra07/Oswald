"""Unit tests for LLM exception hierarchy."""

from oswald.core.llm.exceptions import (
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
)


def test_llm_error_base_attributes() -> None:
    """Verify LLMError initialization and attributes."""
    err = LLMError("API failure", model="gemini/gemini-2.0-flash")
    assert str(err) == "API failure"
    assert err.model == "gemini/gemini-2.0-flash"
    assert isinstance(err, Exception)


def test_llm_provider_error_attributes_and_inheritance() -> None:
    """Verify LLMProviderError inheritance and metadata binding."""
    err = LLMProviderError(
        "Internal server error",
        model="claude-3-5-sonnet",
        status_code=500,
        is_retryable=True,
    )
    assert isinstance(err, LLMError)
    assert str(err) == "Internal server error"
    assert err.model == "claude-3-5-sonnet"
    assert err.status_code == 500
    assert err.is_retryable is True

    # Default optional parameters
    default_err = LLMProviderError("Fatal bad request")
    assert default_err.status_code is None
    assert default_err.is_retryable is False
    assert default_err.model == ""


def test_llm_rate_limit_error_attributes_and_inheritance() -> None:
    """Verify LLMRateLimitError inheritance and retry_after_seconds binding."""
    err = LLMRateLimitError(
        "Rate limit hit",
        model="gpt-4o",
        retry_after_seconds=5.5,
    )
    assert isinstance(err, LLMError)
    assert str(err) == "Rate limit hit"
    assert err.model == "gpt-4o"
    assert err.retry_after_seconds == 5.5

    # Default retry_after_seconds
    default_err = LLMRateLimitError("Too Many Requests")
    assert default_err.retry_after_seconds is None
    assert default_err.model == ""
