"""Política de recuperação semântica independente do índice vetorial."""

from collections.abc import Sequence

from chatbot.application.ports import EmbeddingPort, VectorIndexPort
from chatbot.domain.models import RetrievedChunk


class SemanticRetriever:
    """Orquestra embedding, busca, expansão de páginas e deduplicação."""

    def __init__(
        self,
        *,
        embedding: EmbeddingPort,
        index: VectorIndexPort,
        following_pages: int = 0,
    ) -> None:
        if following_pages < 0:
            raise ValueError("following_pages não pode ser negativo")
        self._embedding = embedding
        self._index = index
        self._following_pages = following_pages

    async def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        vectors = await self._embedding.embed([query])
        if len(vectors) != 1:
            raise RuntimeError("o provedor deve retornar exatamente um embedding para a consulta")

        base_results = await self._index.query(
            vectors[0],
            limit=limit,
            score_threshold=score_threshold,
        )
        results: list[RetrievedChunk] = []
        seen_ids: set[str] = set()
        for result in base_results:
            if result.chunk.id in seen_ids:
                continue
            results.append(result)
            seen_ids.add(result.chunk.id)
            neighbors = await self._index.pages_after(
                result.chunk,
                self._following_pages,
            )
            for chunk in neighbors:
                if chunk.id in seen_ids:
                    continue
                results.append(RetrievedChunk(chunk=chunk, score=result.score))
                seen_ids.add(chunk.id)
        return tuple(results)
