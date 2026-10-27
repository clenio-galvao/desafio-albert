"""Persistência vetorial no Qdrant Cloud."""

from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient, models

from chatbot.application.ports import EmbeddingPort
from chatbot.domain.models import DocumentChunk, RetrievedChunk


class QdrantVectorStore:
    """Adapter único para ingestão e recuperação semântica."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        collection_name: str,
        embedding: EmbeddingPort,
    ) -> None:
        self._collection_name = collection_name
        self._embedding = embedding
        self._client = AsyncQdrantClient(
            url=url,
            api_key=api_key,
            check_compatibility=False,
        )

    async def existing_hashes(self, hashes: Sequence[str]) -> set[str]:
        if not hashes or not await self._client.collection_exists(self._collection_name):
            return set()

        existing: set[str] = set()
        for start in range(0, len(hashes), 256):
            batch = list(hashes[start : start + 256])
            records, _ = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="content_hash",
                            match=models.MatchAny(any=batch),
                        )
                    ]
                ),
                limit=len(batch),
                with_payload=["content_hash"],
                with_vectors=False,
            )
            existing.update(
                str(record.payload["content_hash"])
                for record in records
                if record.payload and "content_hash" in record.payload
            )
        return existing

    async def upsert(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks e vectors devem possuir o mesmo tamanho")
        if not chunks:
            return

        dimension = len(vectors[0])
        if dimension < 1 or any(len(vector) != dimension for vector in vectors):
            raise ValueError("todos os vetores devem ter a mesma dimensão não vazia")
        await self._ensure_collection(dimension)

        points = [
            models.PointStruct(
                id=chunk.id,
                vector=list(vector),
                payload={
                    "text": chunk.text,
                    "source": chunk.source,
                    "page": chunk.page,
                    "content_hash": chunk.content_hash,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await self._client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )

    async def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        if not await self._client.collection_exists(self._collection_name):
            return ()

        vectors = await self._embedding.embed([query])
        if len(vectors) != 1:
            raise RuntimeError("o provedor deve retornar exatamente um embedding para a consulta")
        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=vectors[0],
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        results: list[RetrievedChunk] = []
        for point in response.points:
            payload = point.payload or {}
            chunk = DocumentChunk(
                id=str(point.id),
                text=str(payload["text"]),
                source=str(payload["source"]),
                page=int(payload["page"]),
                content_hash=str(payload["content_hash"]),
            )
            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=max(0.0, min(1.0, float(point.score))),
                )
            )
        return tuple(results)

    async def close(self) -> None:
        await self._client.close()

    async def ready(self) -> bool:
        return await self._client.collection_exists(self._collection_name)

    async def _ensure_collection(self, dimension: int) -> None:
        if await self._client.collection_exists(self._collection_name):
            collection = await self._client.get_collection(self._collection_name)
            vectors = collection.config.params.vectors
            if not isinstance(vectors, models.VectorParams) or vectors.size != dimension:
                raise ValueError("a dimensão do embedding difere da coleção existente")
            return

        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )
