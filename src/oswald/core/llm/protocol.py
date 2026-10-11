"""LLMClient protocol — the sole contract between agents and LLM providers."""

from typing import Protocol, runtime_checkable

from oswald.core.llm.types import LLMRequest, LLMResponse


@runtime_checkable
class LLMClient(Protocol):
    """Provider-agnostic LLM client protocol.

    Any adapter (LiteLLM, fake double, etc.) implements this interface.
    Agent code depends exclusively on this protocol, never on concrete adapters.
    """

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute a single LLM completion and return a neutral response.

        Args:
            request: Provider-neutral request with model, messages, tools, and parameters.

        Returns:
            Provider-neutral response with content, tool calls, usage, and stop reason.

        Raises:
            LLMError: Base exception for all LLM-related failures.
            LLMRateLimitError: Provider rate limit hit (HTTP 429).
            LLMProviderError: Provider 5xx error or fatal API error.
        """
        ...
