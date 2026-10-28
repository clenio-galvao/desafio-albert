"""Streaming de chat pelo protocolo OpenAI-compatible."""

from collections.abc import AsyncIterator, Sequence
from typing import cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from chatbot.application.models import PromptMessage


class OpenAIChatAdapter:
    """Converte mensagens do domínio para chat completions com streaming."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 60,
        max_retries: int = 2,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[PromptMessage],
    ) -> AsyncIterator[str]:
        request_messages = [
            cast(
                ChatCompletionMessageParam,
                {"role": message.role.value, "content": message.content},
            )
            for message in messages
        ]
        response = await self._client.chat.completions.create(
            model=model,
            messages=request_messages,
            stream=True,
        )
        async for chunk in response:
            if chunk.choices and (content := chunk.choices[0].delta.content):
                yield content

    async def close(self) -> None:
        await self._client.close()
