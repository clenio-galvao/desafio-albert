from collections.abc import Sequence
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from qdrant_client import models

from chatbot.adapters.outbound.qdrant import QdrantVectorStore
from chatbot.application.chunking import TokenChunker
from chatbot.application.models import SourcePage
from chatbot.application.use_cases import IngestionService

from ..fakes import FakeDocumentSource, FakeEmbedding


class CharacterEncoding:
    def encode(self, text: str) -> list[int]:
        return [ord(character) for character in text]

    def decode(self, tokens: Sequence[int]) -> str:
        return "".join(chr(token) for token in tokens)


async def test_reingestion_skips_embeddings_through_qdrant_adapter() -> None:
    page = SourcePage(source="apostila.pdf", page=1, text="conteúdo indexável")
    chunker = TokenChunker(
        chunk_size=100,
        overlap=0,
        encoding=CharacterEncoding(),
    )
    chunk = chunker.split([page])[0]
    client = AsyncMock()
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
        ),
    )
    client.scroll.side_effect = [
        ([], None),
        ([SimpleNamespace(payload={"content_hash": chunk.content_hash})], None),
    ]
    embedding = FakeEmbedding()
    with patch(
        "chatbot.adapters.outbound.qdrant.AsyncQdrantClient",
        return_value=client,
    ):
        store = QdrantVectorStore(
            url="https://qdrant.test",
            api_key="secret",
            collection_name="knowledge-v1",
            embedding=embedding,
        )
    service = IngestionService(
        source=FakeDocumentSource([page]),
        chunker=chunker,
        embedding=embedding,
        vector_store=store,
    )

    first = await service.execute()
    second = await service.execute()

    assert first.embedded_chunks == 1
    assert second.embedded_chunks == 0
    assert second.skipped_chunks == 1
    assert embedding.inputs == ["conteúdo indexável"]
    client.upsert.assert_awaited_once()
