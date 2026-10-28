"""Indexa os PDFs locais no Qdrant; nenhuma chamada ocorre por importação."""

import asyncio
import json
from dataclasses import asdict

from chatbot.bootstrap import build_ingestion
from chatbot.config import Settings


async def ingest() -> None:
    """Executa a ingestão offline e imprime o resumo em JSON."""
    container = build_ingestion(Settings())

    try:
        result = await container.ingestion.execute()
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))  # noqa: T201
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(ingest())
