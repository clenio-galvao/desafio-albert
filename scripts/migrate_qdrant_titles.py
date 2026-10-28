"""Preenche títulos ausentes nos payloads já persistidos no Qdrant."""

from collections import defaultdict
from uuid import UUID

from qdrant_client import QdrantClient

from chatbot.adapters.outbound.documents import resolve_document_title
from chatbot.config import Settings


def main() -> None:
    """Preenche `title` nos pontos antigos sem recalcular embeddings."""
    settings = Settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
    )
    points_by_title: dict[str, list[str | int | UUID]] = defaultdict(list)
    offset: str | int | UUID | None = None

    try:
        while True:
            points, offset = client.scroll(
                collection_name=settings.qdrant_collection,
                limit=256,
                offset=offset,
                with_payload=["source", "title"],
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                if payload.get("title"):
                    continue
                source = str(payload.get("source", "documento"))
                points_by_title[resolve_document_title(source)].append(point.id)
            if offset is None:
                break

        migrated = 0
        for title, point_ids in points_by_title.items():
            client.set_payload(
                collection_name=settings.qdrant_collection,
                payload={"title": title},
                points=point_ids,
                wait=True,
            )
            migrated += len(point_ids)
        print(f"Migração concluída: {migrated} payloads atualizados.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
