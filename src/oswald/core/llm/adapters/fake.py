"""Deterministic fake LLM client for unit and integration testing.

Allows test suites to enqueue predetermined responses or exceptions
and inspect recorded requests without performing real network I/O.
"""

from collections import deque

from oswald.core.llm.exceptions import LLMError
from oswald.core.llm.types import LLMRequest, LLMResponse, StopReason, TokenUsage


class FakeLLMClient:
    """Deterministic test double implementing LLMClient via a FIFO response queue."""

    def __init__(self) -> None:
        self._responses: deque[LLMResponse | Exception] = deque()
        self.requests: list[LLMRequest] = []

    def enqueue(self, response: LLMResponse | Exception) -> None:
        """Enqueue a response model or exception to be yielded by complete()."""
        self._responses.append(response)

    def enqueue_text(self, text: str, *, model: str = "fake/test-model") -> None:
        """Convenience method to enqueue a basic text response with default token metrics."""
        self._responses.append(
            LLMResponse(
                content=text,
                stop_reason=StopReason.END_TURN,
                usage=TokenUsage(
                    prompt_tokens=10,
                    completion_tokens=len(text),
                    total_tokens=10 + len(text),
                ),
                model=model,
            )
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Record the request and return or raise the next queued response item."""
        self.requests.append(request)
        if not self._responses:
            raise LLMError("FakeLLMClient: no responses enqueued", model=request.model)
        item = self._responses.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def call_count(self) -> int:
        """Return the number of requests recorded so far."""
        return len(self.requests)
