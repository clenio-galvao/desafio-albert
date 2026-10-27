from collections.abc import Sequence

import pytest

from chatbot.application.chunking import TokenChunker
from chatbot.application.models import SourcePage
from chatbot.application.use_cases import IngestionService

from ..fakes import FakeDocumentSource, FakeEmbedding, FakeVectorStore


class CharacterEncoding:
    def encode(self, text: str) -> list[int]:
        return [ord(character) for character in text]

    def decode(self, tokens: Sequence[int]) -> str:
        return "".join(chr(token) for token in tokens)


class EmptyDecoding:
    def encode(self, text: str) -> list[int]:
        return [1]

    def decode(self, tokens: Sequence[int]) -> str:
        return " "


def make_chunker(chunk_size: int, overlap: int) -> TokenChunker:
    return TokenChunker(
        chunk_size=chunk_size,
        overlap=overlap,
        encoding=CharacterEncoding(),
    )


def test_chunker_is_deterministic_and_preserves_metadata() -> None:
    chunker = make_chunker(chunk_size=4, overlap=1)
    page = SourcePage(
        source="apostila.pdf",
        page=2,
        text="saúde mental depende também de vínculos e cuidado contínuo",
    )

    first = chunker.split([page])
    second = chunker.split([page])

    assert len(first) > 1
    assert first == second
    assert all(chunk.source == "apostila.pdf" and chunk.page == 2 for chunk in first)
    assert len({chunk.id for chunk in first}) == len(first)


def test_chunker_skips_empty_pages() -> None:
    chunker = make_chunker(chunk_size=10, overlap=0)

    assert chunker.split([SourcePage(source="vazio.pdf", page=1, text="")]) == ()


def test_chunker_skips_tokens_that_decode_to_whitespace() -> None:
    chunker = TokenChunker(chunk_size=10, overlap=0, encoding=EmptyDecoding())

    assert chunker.split([SourcePage(source="vazio.pdf", page=1, text="conteúdo")]) == ()


@pytest.mark.parametrize(
    ("chunk_size", "overlap", "message"),
    [(0, 0, "chunk_size"), (5, -1, "overlap"), (5, 5, "overlap")],
)
def test_chunker_validates_configuration(
    chunk_size: int,
    overlap: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        TokenChunker(chunk_size=chunk_size, overlap=overlap)


async def test_ingestion_embeds_and_stores_only_new_chunks() -> None:
    pages = [
        SourcePage(source="a.pdf", page=1, text="primeiro texto"),
        SourcePage(source="b.pdf", page=1, text="segundo texto"),
    ]
    source = FakeDocumentSource(pages)
    chunker = make_chunker(chunk_size=100, overlap=10)
    embedding = FakeEmbedding()
    store = FakeVectorStore()
    existing_chunk = chunker.split(pages[:1])[0]
    store.stored[existing_chunk.id] = (existing_chunk, (1.0, 1.0))
    service = IngestionService(
        source=source,
        chunker=chunker,
        embedding=embedding,
        vector_store=store,
    )

    result = await service.execute()

    assert result.documents == 2
    assert result.chunks == 2
    assert result.embedded_chunks == 1
    assert result.skipped_chunks == 1
    assert embedding.inputs == ["segundo texto"]
    assert len(store.stored) == 2
    assert store.indexes_ensured is True


async def test_ingestion_does_not_call_embedding_when_everything_exists() -> None:
    pages = [SourcePage(source="a.pdf", page=1, text="texto")]
    chunker = make_chunker(chunk_size=100, overlap=0)
    store = FakeVectorStore()
    chunk = chunker.split(pages)[0]
    store.stored[chunk.id] = (chunk, (1.0, 1.0))
    embedding = FakeEmbedding()
    service = IngestionService(
        source=FakeDocumentSource(pages),
        chunker=chunker,
        embedding=embedding,
        vector_store=store,
    )

    result = await service.execute()

    assert result.embedded_chunks == 0
    assert result.skipped_chunks == 1
    assert embedding.inputs == []


class BrokenEmbedding:
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return []


async def test_ingestion_rejects_incomplete_embedding_response() -> None:
    service = IngestionService(
        source=FakeDocumentSource([SourcePage(source="a.pdf", page=1, text="texto")]),
        chunker=make_chunker(chunk_size=100, overlap=0),
        embedding=BrokenEmbedding(),
        vector_store=FakeVectorStore(),
    )

    with pytest.raises(RuntimeError, match="quantidade de embeddings"):
        await service.execute()
