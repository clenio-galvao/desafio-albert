from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from qdrant_client import models

from chatbot.adapters.outbound.qdrant import QdrantVectorStore
from chatbot.domain.models import DocumentChunk


def make_chunk(identifier: str = "00000000-0000-0000-0000-000000000001") -> DocumentChunk:
    return DocumentChunk(
        id=identifier,
        text="conteúdo",
        source="apostila.pdf",
        title="Apostila",
        page=1,
        content_hash=f"hash-{identifier}",
    )


def make_store() -> tuple[QdrantVectorStore, AsyncMock]:
    client = AsyncMock()
    with patch(
        "chatbot.adapters.outbound.qdrant.AsyncQdrantClient",
        return_value=client,
    ):
        store = QdrantVectorStore(
            url="https://qdrant.test",
            api_key="secret",
            collection_name="knowledge-v1",
        )
    return store, client


async def test_existing_hashes_short_circuits_empty_or_missing_collection() -> None:
    store, client = make_store()

    assert await store.existing_hashes([]) == set()
    client.collection_exists.assert_not_awaited()

    client.collection_exists.return_value = False
    assert await store.existing_hashes(["hash"]) == set()
    client.scroll.assert_not_awaited()


async def test_ensure_indexes_skips_missing_collection_and_creates_missing_fields() -> None:
    store, client = make_store()
    client.collection_exists.return_value = False
    await store.ensure_indexes()
    client.get_collection.assert_not_awaited()

    client.collection_exists.return_value = True
    client.get_collection.return_value = SimpleNamespace(
        payload_schema={
            "content_hash": object(),
            "source": object(),
        }
    )
    await store.ensure_indexes()

    client.create_payload_index.assert_awaited_once()
    assert client.create_payload_index.await_args.kwargs["field_name"] == "page"


async def test_existing_hashes_reads_payload_in_batches() -> None:
    store, client = make_store()
    client.collection_exists.return_value = True
    client.scroll.side_effect = [
        ([SimpleNamespace(payload={"content_hash": "hash-0"})], None),
        (
            [
                SimpleNamespace(payload={"content_hash": "hash-256"}),
                SimpleNamespace(payload=None),
            ],
            None,
        ),
    ]

    result = await store.existing_hashes([f"hash-{index}" for index in range(257)])

    assert result == {"hash-0", "hash-256"}
    assert client.scroll.await_count == 2


async def test_upsert_creates_collection_and_writes_payload() -> None:
    store, client = make_store()
    client.collection_exists.side_effect = [False, True]
    client.get_collection.return_value = SimpleNamespace(payload_schema={})
    chunk = make_chunk()

    await store.upsert([chunk], [[0.1, 0.2]])

    client.create_collection.assert_awaited_once()
    assert client.create_payload_index.await_count == 3
    upsert_call = client.upsert.await_args.kwargs
    assert upsert_call["collection_name"] == "knowledge-v1"
    assert upsert_call["wait"] is True
    assert upsert_call["points"][0].payload["source"] == "apostila.pdf"
    assert upsert_call["points"][0].payload["title"] == "Apostila"


async def test_upsert_validates_input_shapes_and_empty_input() -> None:
    store, client = make_store()
    chunk = make_chunk()

    with pytest.raises(ValueError, match="mesmo tamanho"):
        await store.upsert([chunk], [])
    await store.upsert([], [])
    client.collection_exists.assert_not_awaited()

    with pytest.raises(ValueError, match="mesma dimensão"):
        await store.upsert([chunk], [[]])
    with pytest.raises(ValueError, match="mesma dimensão"):
        await store.upsert(
            [chunk, make_chunk("00000000-0000-0000-0000-000000000002")],
            [[1.0], [1.0, 2.0]],
        )


async def test_upsert_accepts_existing_collection_with_matching_dimension() -> None:
    store, client = make_store()
    client.collection_exists.return_value = True
    client.get_collection.return_value = SimpleNamespace(
        payload_schema={
            "content_hash": object(),
            "source": object(),
            "page": object(),
        },
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=models.VectorParams(size=2, distance=models.Distance.COSINE)
            )
        )
    )

    await store.upsert([make_chunk()], [[0.1, 0.2]])

    client.create_collection.assert_not_awaited()
    client.upsert.assert_awaited_once()


@pytest.mark.parametrize(
    "vectors",
    [
        models.VectorParams(size=3, distance=models.Distance.COSINE),
        {"named": models.VectorParams(size=2, distance=models.Distance.COSINE)},
    ],
)
async def test_upsert_rejects_incompatible_existing_collection(vectors: object) -> None:
    store, client = make_store()
    client.collection_exists.return_value = True
    client.get_collection.return_value = SimpleNamespace(
        payload_schema={
            "content_hash": object(),
            "source": object(),
            "page": object(),
        },
        config=SimpleNamespace(params=SimpleNamespace(vectors=vectors))
    )

    with pytest.raises(ValueError, match="dimensão"):
        await store.upsert([make_chunk()], [[0.1, 0.2]])


async def test_search_short_circuits_missing_collection() -> None:
    store, client = make_store()
    client.collection_exists.return_value = False

    assert await store.query([0.1, 0.2], limit=3, score_threshold=0.7) == ()


async def test_query_maps_vector_results() -> None:
    store, client = make_store()
    client.collection_exists.return_value = True
    client.query_points.return_value = SimpleNamespace(
        points=[
            SimpleNamespace(
                id="00000000-0000-0000-0000-000000000001",
                score=1.2,
                payload={
                    "text": "conteúdo",
                    "source": "apostila.pdf",
                    "title": "Apostila",
                    "page": 4,
                    "content_hash": "hash",
                },
            )
        ]
    )

    results = await store.query([0.1, 0.2], limit=3, score_threshold=0.7)

    assert results[0].score == 1
    assert results[0].chunk.page == 4
    assert results[0].chunk.title == "Apostila"
    assert client.query_points.await_args.kwargs["query"] == [0.1, 0.2]


async def test_pages_after_reads_consecutive_document_pages() -> None:
    store, client = make_store()
    following_record = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000002",
        payload={
            "text": "continuação da lista",
            "source": "apostila.pdf",
            "title": "Apostila",
            "page": 5,
            "content_hash": "hash-5",
        },
    )
    client.scroll.side_effect = [
        ([following_record], None),
        ([following_record], None),
    ]

    results = await store.pages_after(make_chunk(), 2)

    assert [chunk.page for chunk in results] == [5, 5]
    assert client.scroll.await_count == 2


async def test_close_releases_qdrant_client() -> None:
    store, client = make_store()

    await store.close()

    client.close.assert_awaited_once()


async def test_ready_checks_collection() -> None:
    store, client = make_store()
    client.collection_exists.return_value = True

    assert await store.ready() is True
    client.collection_exists.assert_awaited_once_with("knowledge-v1")
