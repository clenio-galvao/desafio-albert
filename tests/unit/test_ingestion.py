from collections.abc import Sequence

import pytest

from chatbot.application.chunking import TokenChunker
from chatbot.application.models import SourcePage
from chatbot.application.use_cases import IngestionService

from ..fakes import CharacterEncoding, FakeDocumentSource, FakeEmbedding, FakeVectorStore


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


def _long_page() -> SourcePage:
    return SourcePage(
        source="apostila.pdf",
        title="Apostila",
        page=2,
        text="saúde mental depende também de vínculos e cuidado contínuo",
    )


def test_chunker_is_deterministic() -> None:
    chunker = make_chunker(chunk_size=4, overlap=1)

    assert chunker.split([_long_page()]) == chunker.split([_long_page()])


def test_chunker_preserves_page_metadata() -> None:
    chunks = make_chunker(chunk_size=4, overlap=1).split([_long_page()])

    assert len(chunks) > 1
    assert all(chunk.source == "apostila.pdf" and chunk.page == 2 for chunk in chunks)


def test_chunker_assigns_unique_ids() -> None:
    chunks = make_chunker(chunk_size=4, overlap=1).split([_long_page()])

    assert len({chunk.id for chunk in chunks}) == len(chunks)


def test_chunker_assigns_sequential_positions() -> None:
    chunks = make_chunker(chunk_size=4, overlap=1).split([_long_page()])

    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))


def test_chunker_restarts_position_on_each_page() -> None:
    chunker = make_chunker(chunk_size=4, overlap=0)
    pages = [
        SourcePage(source="a.pdf", title="A", page=1, text="abcdefgh"),
        SourcePage(source="a.pdf", title="A", page=2, text="ijklmnop"),
    ]

    chunks = chunker.split(pages)

    assert [(chunk.page, chunk.position) for chunk in chunks] == [(1, 0), (1, 1), (2, 0), (2, 1)]


def test_chunker_skips_empty_pages() -> None:
    chunker = make_chunker(chunk_size=10, overlap=0)

    assert chunker.split(
        [SourcePage(source="vazio.pdf", title="Vazio", page=1, text="")]
    ) == ()


def test_chunker_skips_tokens_that_decode_to_whitespace() -> None:
    chunker = TokenChunker(chunk_size=10, overlap=0, encoding=EmptyDecoding())

    assert chunker.split(
        [SourcePage(source="vazio.pdf", title="Vazio", page=1, text="conteúdo")]
    ) == ()


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
        TokenChunker(
            chunk_size=chunk_size,
            overlap=overlap,
            encoding=CharacterEncoding(),
        )


async def test_ingestion_embeds_and_stores_only_new_chunks() -> None:
    pages = [
        SourcePage(source="a.pdf", title="A", page=1, text="primeiro texto"),
        SourcePage(source="b.pdf", title="B", page=1, text="segundo texto"),
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
    pages = [SourcePage(source="a.pdf", title="A", page=1, text="texto")]
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
        source=FakeDocumentSource(
            [SourcePage(source="a.pdf", title="A", page=1, text="texto")]
        ),
        chunker=make_chunker(chunk_size=100, overlap=0),
        embedding=BrokenEmbedding(),
        vector_store=FakeVectorStore(),
    )

    with pytest.raises(RuntimeError, match="quantidade de embeddings"):
        await service.execute()
