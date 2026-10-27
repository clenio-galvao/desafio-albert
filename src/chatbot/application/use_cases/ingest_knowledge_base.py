"""Caso de uso idempotente de ingestão da base de conhecimento."""

from chatbot.application.chunking import TokenChunker
from chatbot.application.models import IngestionResult
from chatbot.application.ports import DocumentSourcePort, EmbeddingPort, VectorStorePort


class IngestionService:
    """Coordena leitura, chunking, deduplicação, embeddings e persistência."""

    def __init__(
        self,
        *,
        source: DocumentSourcePort,
        chunker: TokenChunker,
        embedding: EmbeddingPort,
        vector_store: VectorStorePort,
    ) -> None:
        self._source = source
        self._chunker = chunker
        self._embedding = embedding
        self._vector_store = vector_store

    async def execute(self) -> IngestionResult:
        pages = await self._source.load()
        chunks = self._chunker.split(pages)
        hashes = tuple(chunk.content_hash for chunk in chunks)
        existing = await self._vector_store.existing_hashes(hashes)
        pending = tuple(chunk for chunk in chunks if chunk.content_hash not in existing)

        if pending:
            vectors = await self._embedding.embed([chunk.text for chunk in pending])
            if len(vectors) != len(pending):
                raise RuntimeError("a quantidade de embeddings não corresponde aos chunks")
            await self._vector_store.upsert(pending, vectors)

        return IngestionResult(
            documents=len({page.source for page in pages}),
            chunks=len(chunks),
            embedded_chunks=len(pending),
            skipped_chunks=len(chunks) - len(pending),
        )
