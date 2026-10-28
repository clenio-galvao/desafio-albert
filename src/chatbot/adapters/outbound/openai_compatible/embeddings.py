"""Embeddings em lote usando o protocolo OpenAI-compatible."""

from collections.abc import Sequence

from openai import AsyncOpenAI


class OpenAIEmbeddingAdapter:
    """Gera vetores preservando a ordem das entradas."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        batch_size: int = 32,
        timeout_seconds: float = 30,
        max_retries: int = 2,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size deve ser maior que zero")
        self._model = model
        self._batch_size = batch_size
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Gera vetores em lotes e restaura a ordem original das entradas."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            response = await self._client.embeddings.create(model=self._model, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(batch):
                raise RuntimeError("o provedor retornou uma quantidade inesperada de embeddings")
            vectors.extend(item.embedding for item in ordered)
        return vectors

    async def close(self) -> None:
        """Encerra o cliente HTTP do gateway de embeddings."""
        await self._client.close()
