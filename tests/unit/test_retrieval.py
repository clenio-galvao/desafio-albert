from collections.abc import Sequence

import pytest

from chatbot.application.retrieval import SemanticRetriever
from chatbot.domain import DocumentChunk, RetrievedChunk

from ..fakes import FakeEmbedding


def make_chunk(identifier: str, page: int) -> DocumentChunk:
    return DocumentChunk(
        id=identifier,
        text=f"página {page}",
        source="apostila.pdf",
        title="Apostila",
        page=page,
        content_hash=f"hash-{identifier}",
    )


class FakeIndex:
    def __init__(
        self,
        results: Sequence[RetrievedChunk] = (),
        following: Sequence[DocumentChunk] = (),
    ) -> None:
        self.results = tuple(results)
        self.following = tuple(following)
        self.vectors: list[tuple[float, ...]] = []
        self.counts: list[int] = []

    async def query(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        self.vectors.append(tuple(vector))
        return self.results[:limit]

    async def pages_after(
        self,
        chunk: DocumentChunk,
        count: int,
    ) -> Sequence[DocumentChunk]:
        self.counts.append(count)
        return self.following


def test_semantic_retriever_rejects_negative_page_expansion() -> None:
    with pytest.raises(ValueError, match="following_pages"):
        SemanticRetriever(
            embedding=FakeEmbedding(),
            index=FakeIndex(),
            following_pages=-1,
        )


async def test_semantic_retriever_embeds_expands_and_deduplicates() -> None:
    first = make_chunk("first", 1)
    second = make_chunk("second", 2)
    embedding = FakeEmbedding()
    index = FakeIndex(
        results=(
            RetrievedChunk(chunk=first, score=0.9),
            RetrievedChunk(chunk=second, score=0.8),
        ),
        following=(second,),
    )
    retriever = SemanticRetriever(
        embedding=embedding,
        index=index,
        following_pages=1,
    )

    results = await retriever.search("pergunta", limit=3, score_threshold=0.35)

    assert embedding.inputs == ["pergunta"]
    assert index.vectors == [(8.0, 1.0)]
    assert index.counts == [1]
    assert [result.chunk.id for result in results] == ["first", "second"]
    assert results[1].score == 0.9


async def test_semantic_retriever_rejects_invalid_embedding_response() -> None:
    embedding = FakeEmbedding()

    async def broken_embed(texts: Sequence[str]) -> list[list[float]]:
        return []

    embedding.embed = broken_embed  # type: ignore[method-assign]
    retriever = SemanticRetriever(embedding=embedding, index=FakeIndex())

    with pytest.raises(RuntimeError, match="exatamente um"):
        await retriever.search("pergunta", limit=3, score_threshold=0.35)


async def test_semantic_retriever_ignores_repeated_neighbor() -> None:
    chunk = make_chunk("first", 1)
    retriever = SemanticRetriever(
        embedding=FakeEmbedding(),
        index=FakeIndex(
            results=(RetrievedChunk(chunk=chunk, score=0.9),),
            following=(chunk,),
        ),
        following_pages=1,
    )

    results = await retriever.search("pergunta", limit=3, score_threshold=0.35)

    assert [result.chunk.id for result in results] == ["first"]
