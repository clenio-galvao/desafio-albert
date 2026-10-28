"""Dublês determinísticos para medir a API sem gateway, Qdrant ou cota."""

import asyncio
from collections.abc import AsyncIterator, Sequence

from chatbot.application.models import PromptMessage
from chatbot.domain.models import DocumentChunk, RetrievedChunk


class LoadLLM:
    """Gera tokens locais, com atraso opcional para simular streaming."""

    def __init__(
        self,
        tokens: Sequence[str] = ("resposta ", "fundada ", "local."),
        delay_seconds: float = 0.0,
    ) -> None:
        self._tokens = tuple(tokens)
        self._delay_seconds = delay_seconds

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[PromptMessage],
    ) -> AsyncIterator[str]:
        """Emite tokens locais, opcionalmente espaçados para simular latência."""
        del model, messages
        for token in self._tokens:
            if self._delay_seconds > 0:
                await asyncio.sleep(self._delay_seconds)
            yield token


class LoadRetriever:
    """Devolve evidência fixa sem embedding nem índice vetorial."""

    def __init__(self, results: Sequence[RetrievedChunk] | None = None) -> None:
        chunk = DocumentChunk(
            id="00000000-0000-0000-0000-000000000001",
            text="A escuta terapêutica é uma prática de cuidado.",
            source="apostila.pdf",
            title="Apostila de carga",
            page=1,
            content_hash="load-hash",
        )
        self._results = tuple(results) if results is not None else (
            RetrievedChunk(chunk=chunk, score=0.9),
        )

    async def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Ignora a consulta e devolve evidência fixa até o limite pedido."""
        del query, score_threshold
        return self._results[:limit]


class AlwaysReady:
    """Dependência de prontidão que nunca falha no perfil de carga."""

    async def ready(self) -> bool:
        """Sempre indica que a base fictícia está disponível."""
        return True
