"""Persistência vetorial no Qdrant Cloud."""

from collections.abc import Sequence
from typing import cast

from qdrant_client import AsyncQdrantClient, models

from chatbot.domain.models import DocumentChunk, RetrievedChunk

# O scroll do Qdrant ordena por ID (uuid5, sem relação com a ordem do texto), então
# todos os chunks das páginas seguintes precisam ser lidos para achar o primeiro.
_NEIGHBOR_SCAN_LIMIT = 64


class QdrantVectorStore:
    """Adapter único para ingestão e recuperação semântica."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        collection_name: str,
    ) -> None:
        self._collection_name = collection_name
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
                    "title": chunk.title,
                    "page": chunk.page,
                    "position": chunk.position,
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

    async def query(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        if not await self._client.collection_exists(self._collection_name):
            return ()

        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=list(vector),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        results: list[RetrievedChunk] = []
        for point in response.points:
            identifier = str(point.id)
            payload = point.payload or {}
            chunk = self._payload_to_chunk(identifier, payload)
            score = max(0.0, min(1.0, float(point.score)))
            results.append(RetrievedChunk(chunk=chunk, score=score))
        return tuple(results)

    async def close(self) -> None:
        await self._client.close()

    async def ready(self) -> bool:
        return await self._client.collection_exists(self._collection_name)

    async def pages_after(
        self,
        chunk: DocumentChunk,
        count: int,
    ) -> Sequence[DocumentChunk]:
        if count < 1:
            return ()
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
                        range=models.Range(gt=chunk.page, lte=chunk.page + count),
                    ),
                ]
            ),
            limit=_NEIGHBOR_SCAN_LIMIT,
            with_payload=True,
            with_vectors=False,
        )
        first_by_page: dict[int, DocumentChunk] = {}
        for record in records:
            candidate = self._payload_to_chunk(str(record.id), record.payload or {})
            current = first_by_page.get(candidate.page)
            if current is None or candidate.position < current.position:
                first_by_page[candidate.page] = candidate
        return tuple(first_by_page[page] for page in sorted(first_by_page))

    @staticmethod
    def _payload_to_chunk(identifier: str, payload: dict[str, object]) -> DocumentChunk:
        return DocumentChunk(
            id=identifier,
            text=str(payload["text"]),
            source=str(payload["source"]),
            title=str(payload["title"]),
            page=int(cast(int | str, payload["page"])),
            content_hash=str(payload["content_hash"]),
            position=int(cast(int | str, payload.get("position", 0))),
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
