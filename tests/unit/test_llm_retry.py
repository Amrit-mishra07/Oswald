"""Unit tests for exponential backoff and retry logic."""

from typing import Any

import pytest

from oswald.core.llm.adapters.litellm_adapter import (
    RetryConfig,
    _compute_delay,
    retry_with_backoff,
)
from oswald.core.llm.exceptions import (
    LLMProviderError,
    LLMRateLimitError,
)


def test_compute_delay_exponential_growth_and_jitter_bounds() -> None:
    """Verify _compute_delay grows exponentially and stays within jitter bounds."""
    config = RetryConfig(
        base_delay_seconds=1.0,
        max_delay_seconds=10.0,
        jitter_factor=0.5,
    )

    # Attempt 0: base=1.0, cap=1.0, jitter=[0, 0.5] -> [1.0, 1.5]
    for _ in range(50):
        d0 = _compute_delay(0, config)
        assert 1.0 <= d0 <= 1.5

    # Attempt 1: base=2.0, cap=2.0, jitter=[0, 1.0] -> [2.0, 3.0]
    for _ in range(50):
        d1 = _compute_delay(1, config)
        assert 2.0 <= d1 <= 3.0

    # Attempt 2: base=4.0, cap=4.0, jitter=[0, 2.0] -> [4.0, 6.0]
    for _ in range(50):
        d2 = _compute_delay(2, config)
        assert 4.0 <= d2 <= 6.0

    # Large attempt: capped at max_delay_seconds=10.0, jitter=[0, 5.0] -> [10.0, 15.0]
    for _ in range(50):
        d_large = _compute_delay(10, config)
        assert 10.0 <= d_large <= 15.0


def test_compute_delay_zero_jitter() -> None:
    """Verify zero jitter produces exact deterministic delays."""
    config = RetryConfig(
        base_delay_seconds=2.0,
        max_delay_seconds=10.0,
        jitter_factor=0.0,
    )
    assert _compute_delay(0, config) == 2.0
    assert _compute_delay(1, config) == 4.0
    assert _compute_delay(2, config) == 8.0
    assert _compute_delay(3, config) == 10.0  # capped


async def test_retry_success_on_first_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify immediate success does not trigger sleep or retries."""
    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    call_count = 0

    async def operation() -> str:
        nonlocal call_count
        call_count += 1
        return "success"

    res = await retry_with_backoff(operation, RetryConfig(), run_id="run-1")
    assert res == "success"
    assert call_count == 1
    assert sleep_calls == []


async def test_retry_on_rate_limit_with_custom_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify rate limit respects exc.retry_after_seconds when provided."""
    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LLMRateLimitError("Too Many Requests", retry_after_seconds=4.5)
        return "success_after_rate_limit"

    res = await retry_with_backoff(operation, RetryConfig(max_retries=2), run_id="run-2")
    assert res == "success_after_rate_limit"
    assert attempts == 2
    assert sleep_calls == [4.5]


async def test_retry_on_rate_limit_with_computed_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify rate limit without retry_after_seconds falls back to exponential backoff."""
    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LLMRateLimitError("Too Many Requests", retry_after_seconds=None)
        return "recovered"

    res = await retry_with_backoff(
        operation,
        RetryConfig(base_delay_seconds=1.0, jitter_factor=0.0),
        run_id="run-3",
    )
    assert res == "recovered"
    assert attempts == 2
    assert sleep_calls == [1.0]


async def test_retry_on_retryable_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify retryable provider errors (e.g. 503) are retried."""
    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise LLMProviderError("Overloaded", status_code=503, is_retryable=True)
        return "recovered_503"

    res = await retry_with_backoff(
        operation,
        RetryConfig(max_retries=3, base_delay_seconds=1.0, jitter_factor=0.0),
        run_id="run-4",
    )
    assert res == "recovered_503"
    assert attempts == 3
    assert sleep_calls == [1.0, 2.0]


async def test_fast_fail_on_non_retryable_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify non-retryable provider errors (e.g. 400 Bad Request) immediately raise."""
    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    attempts = 0

    async def operation() -> Any:
        nonlocal attempts
        attempts += 1
        raise LLMProviderError("Bad Request", status_code=400, is_retryable=False)

    with pytest.raises(LLMProviderError) as exc_info:
        await retry_with_backoff(operation, RetryConfig(max_retries=3))

    assert exc_info.value.status_code == 400
    assert attempts == 1
    assert sleep_calls == []


async def test_fast_fail_on_non_llm_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify non-LLM exceptions pass through immediately without retrying."""
    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    attempts = 0

    async def operation() -> Any:
        nonlocal attempts
        attempts += 1
        raise ValueError("Unexpected programming error")

    with pytest.raises(ValueError, match="Unexpected programming error"):
        await retry_with_backoff(operation, RetryConfig(max_retries=3))

    assert attempts == 1
    assert sleep_calls == []


async def test_retry_exhaustion_raises_last_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that exceeding max_retries re-raises the final encountered exception."""
    sleep_calls: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    attempts = 0

    async def operation() -> Any:
        nonlocal attempts
        attempts += 1
        raise LLMRateLimitError(f"Rate limit fail {attempts}")

    with pytest.raises(LLMRateLimitError, match="Rate limit fail 3"):
        await retry_with_backoff(operation, RetryConfig(max_retries=2))

    assert attempts == 3  # initial + 2 retries
    assert len(sleep_calls) == 2
