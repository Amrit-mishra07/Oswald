"""Unit tests for FakeLLMClient test double."""

import pytest

from oswald.core.llm.adapters.fake import FakeLLMClient
from oswald.core.llm.exceptions import LLMError, LLMRateLimitError
from oswald.core.llm.protocol import LLMClient
from oswald.core.llm.types import (
    LLMRequest,
    LLMResponse,
    Message,
    Role,
    StopReason,
    TokenUsage,
)


def _make_request(content: str = "Hello", model: str = "fake/model") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[Message(role=Role.USER, content=content)],
    )


async def test_fake_llm_client_satisfies_protocol() -> None:
    """Verify FakeLLMClient structurally conforms to LLMClient Protocol."""
    client = FakeLLMClient()
    assert isinstance(client, LLMClient)


async def test_fake_llm_fifo_ordering() -> None:
    """Verify FIFO ordering when multiple responses are enqueued."""
    client = FakeLLMClient()

    resp1 = LLMResponse(
        content="Response 1",
        stop_reason=StopReason.END_TURN,
        usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
        model="fake/model",
    )
    resp2 = LLMResponse(
        content="Response 2",
        stop_reason=StopReason.TOOL_USE,
        usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
        model="fake/model",
    )

    client.enqueue(resp1)
    client.enqueue(resp2)

    req1 = _make_request("req1")
    req2 = _make_request("req2")

    got1 = await client.complete(req1)
    assert got1 == resp1
    assert client.call_count == 1
    assert client.requests == [req1]

    got2 = await client.complete(req2)
    assert got2 == resp2
    assert client.call_count == 2
    assert client.requests == [req1, req2]


async def test_fake_llm_enqueue_text_convenience() -> None:
    """Verify enqueue_text sets content, default token usage, and model."""
    client = FakeLLMClient()
    client.enqueue_text("Simple text message", model="custom/model")

    req = _make_request()
    res = await client.complete(req)

    assert res.content == "Simple text message"
    assert res.model == "custom/model"
    assert res.stop_reason == StopReason.END_TURN
    assert res.usage.prompt_tokens == 10
    assert res.usage.completion_tokens == len("Simple text message")
    assert res.usage.total_tokens == 10 + len("Simple text message")


async def test_fake_llm_raises_enqueued_exception() -> None:
    """Verify enqueued exceptions are raised when complete() is called."""
    client = FakeLLMClient()
    exc = LLMRateLimitError("Too Many Requests", model="fake/model", retry_after_seconds=2.0)
    client.enqueue(exc)

    req = _make_request()
    with pytest.raises(LLMRateLimitError) as exc_info:
        await client.complete(req)

    assert exc_info.value is exc
    assert client.call_count == 1
    assert client.requests == [req]


async def test_fake_llm_raises_when_queue_empty() -> None:
    """Verify calling complete() on an empty queue raises an informative LLMError."""
    client = FakeLLMClient()
    req = _make_request(model="test/empty-model")

    with pytest.raises(LLMError) as exc_info:
        await client.complete(req)

    assert "no responses enqueued" in str(exc_info.value)
    assert exc_info.value.model == "test/empty-model"
    assert client.call_count == 1
