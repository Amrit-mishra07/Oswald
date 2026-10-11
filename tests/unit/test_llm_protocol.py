"""Unit tests for LLMClient protocol structural typing compliance."""

from oswald.core.llm.adapters.fake import FakeLLMClient
from oswald.core.llm.adapters.litellm_adapter import LiteLLMAdapter
from oswald.core.llm.protocol import LLMClient
from oswald.core.llm.types import LLMRequest, LLMResponse, Message, Role, StopReason


def test_protocol_structural_conformance() -> None:
    """Verify concrete adapters satisfy the LLMClient protocol both statically and at runtime."""
    fake_client = FakeLLMClient()
    litellm_adapter = LiteLLMAdapter(api_key="test-key")

    # Runtime isinstance verification via @runtime_checkable
    assert isinstance(fake_client, LLMClient)
    assert isinstance(litellm_adapter, LLMClient)


async def test_minimal_custom_llm_client_satisfies_protocol() -> None:
    """Verify a minimal custom implementation satisfies LLMClient."""

    class StubClient:
        async def complete(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(content="stub", stop_reason=StopReason.END_TURN)

    stub = StubClient()
    assert isinstance(stub, LLMClient)

    req = LLMRequest(
        model="test",
        messages=[Message(role=Role.USER, content="hello")],
    )
    res = await stub.complete(req)
    assert res.content == "stub"
    assert res.stop_reason == StopReason.END_TURN
