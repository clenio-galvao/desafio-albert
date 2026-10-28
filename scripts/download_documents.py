"""Baixa as apostilas para um diretório ignorado pelo Git."""

import argparse
import asyncio
from pathlib import Path

from chatbot.adapters.outbound.documents import GoogleDriveFolderDownloader

DEFAULT_FOLDER_URL = "https://drive.google.com/drive/folders/1OedUXeWJY9cFTL2DwNmfejYtk12ptz4N"


def parse_args() -> argparse.Namespace:
    """Lê a pasta do Drive e o diretório local de destino."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder-url", default=DEFAULT_FOLDER_URL)
    parser.add_argument("--output", type=Path, default=Path("data/documents"))
    return parser.parse_args()


async def download_documents() -> None:
    """Baixa os PDFs da pasta configurada para `data/documents`."""
    args = parse_args()
    downloader = GoogleDriveFolderDownloader(args.folder_url, args.output)
    paths = await downloader.download()
    print(f"{len(paths)} PDFs baixados em {args.output}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(download_documents())
