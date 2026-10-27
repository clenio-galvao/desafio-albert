"""Indexa os PDFs locais no Qdrant; nenhuma chamada ocorre por importação."""

import asyncio
import json
from dataclasses import asdict

from chatbot.adapters.outbound.documents import PdfDirectorySource
from chatbot.adapters.outbound.openai_compatible import OpenAIEmbeddingAdapter
from chatbot.adapters.outbound.qdrant import QdrantVectorStore
from chatbot.application.chunking import TokenChunker
from chatbot.application.use_cases import IngestionService
from chatbot.config import Settings


async def ingest() -> None:
    settings = Settings()
    embedding = OpenAIEmbeddingAdapter(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
        collection_name=settings.qdrant_collection,
        embedding=embedding,
    )
    service = IngestionService(
        source=PdfDirectorySource(settings.documents_dir),
        chunker=TokenChunker(
            chunk_size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
        ),
        embedding=embedding,
        vector_store=vector_store,
    )

    try:
        result = await service.execute()
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))  # noqa: T201
    finally:
        await vector_store.close()


if __name__ == "__main__":
    asyncio.run(ingest())
