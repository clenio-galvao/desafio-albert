"""Persistência vetorial no Qdrant Cloud."""

from collections.abc import Sequence
from typing import cast

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
        following_pages: int = 0,
    ) -> None:
        if following_pages < 0:
            raise ValueError("following_pages não pode ser negativo")
        self._collection_name = collection_name
        self._embedding = embedding
        self._following_pages = following_pages
        self._client = AsyncQdrantClient(
            url=url,
            api_key=api_key,
            check_compatibility=False,
        )

    async def ensure_indexes(self) -> None:
        if not await self._client.collection_exists(self._collection_name):
            return
        collection = await self._client.get_collection(self._collection_name)
        existing = collection.payload_schema or {}
        required = {
            "content_hash": models.PayloadSchemaType.KEYWORD,
            "source": models.PayloadSchemaType.KEYWORD,
            "page": models.PayloadSchemaType.INTEGER,
        }
        for field_name, field_schema in required.items():
            if field_name in existing:
                continue
            await self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
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
        seen_ids: set[str] = set()
        for point in response.points:
            identifier = str(point.id)
            if identifier in seen_ids:
                continue
            payload = point.payload or {}
            chunk = self._payload_to_chunk(identifier, payload)
            score = max(0.0, min(1.0, float(point.score)))
            results.append(RetrievedChunk(chunk=chunk, score=score))
            seen_ids.add(chunk.id)
            results.extend(
                await self._following_chunks(
                    chunk=chunk,
                    score=score,
                    seen_ids=seen_ids,
                )
            )
        return tuple(results)

    async def close(self) -> None:
        await self._client.close()

    async def ready(self) -> bool:
        return await self._client.collection_exists(self._collection_name)

    async def _following_chunks(
        self,
        *,
        chunk: DocumentChunk,
        score: float,
        seen_ids: set[str],
    ) -> list[RetrievedChunk]:
        neighbors: list[RetrievedChunk] = []
        for offset in range(1, self._following_pages + 1):
            records, _ = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source",
                            match=models.MatchValue(value=chunk.source),
                        ),
                        models.FieldCondition(
                            key="page",
                            match=models.MatchValue(value=chunk.page + offset),
                        ),
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                identifier = str(record.id)
                if identifier in seen_ids:
                    continue
                neighbor = self._payload_to_chunk(identifier, record.payload or {})
                neighbors.append(RetrievedChunk(chunk=neighbor, score=score))
                seen_ids.add(identifier)
        return neighbors

    @staticmethod
    def _payload_to_chunk(identifier: str, payload: dict[str, object]) -> DocumentChunk:
        return DocumentChunk(
            id=identifier,
            text=str(payload["text"]),
            source=str(payload["source"]),
            page=int(cast(int | str, payload["page"])),
            content_hash=str(payload["content_hash"]),
        )

    async def _ensure_collection(self, dimension: int) -> None:
        if await self._client.collection_exists(self._collection_name):
            collection = await self._client.get_collection(self._collection_name)
            vectors = collection.config.params.vectors
            if not isinstance(vectors, models.VectorParams) or vectors.size != dimension:
                raise ValueError("a dimensão do embedding difere da coleção existente")
            await self.ensure_indexes()
            return

        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=models.VectorParams(
                size=dimension,
                distance=models.Distance.COSINE,
            ),
        )
        await self.ensure_indexes()
