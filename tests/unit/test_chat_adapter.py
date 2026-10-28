from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from chatbot.adapters.outbound.openai_compatible.chat import OpenAIChatAdapter
from chatbot.application import PromptMessage, PromptRole


def build_adapter() -> tuple[OpenAIChatAdapter, MagicMock]:
    client = MagicMock()
    client.chat.completions.create = AsyncMock()
    client.close = AsyncMock()
    with patch(
        "chatbot.adapters.outbound.openai_compatible.chat.AsyncOpenAI",
        return_value=client,
    ):
        adapter = OpenAIChatAdapter(
            base_url="https://gateway.test/v1",
            api_key="secret",
        )
    return adapter, client


async def fake_chunks() -> AsyncIterator[object]:
    yield SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="Olá"))]
    )
    yield SimpleNamespace(choices=[])
    yield SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]
    )
    yield SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=" mundo"))]
    )


async def test_chat_adapter_streams_only_content_tokens() -> None:
    adapter, client = build_adapter()
    client.chat.completions.create.return_value = fake_chunks()
    messages = [
        PromptMessage(PromptRole.SYSTEM, "regra"),
        PromptMessage(PromptRole.USER, "pergunta"),
    ]

    tokens = [
        token
        async for token in adapter.stream(
            model="model-a",
            messages=messages,
        )
    ]

    assert tokens == ["Olá", " mundo"]
    call = client.chat.completions.create.await_args.kwargs
    assert call["model"] == "model-a"
    assert call["stream"] is True
    assert call["messages"] == [
        {"role": "system", "content": "regra"},
        {"role": "user", "content": "pergunta"},
    ]


async def test_chat_adapter_closes_client() -> None:
    adapter, client = build_adapter()

    await adapter.close()

    client.close.assert_awaited_once()
