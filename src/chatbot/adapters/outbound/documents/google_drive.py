"""Download explícito de uma pasta pública do Google Drive."""

import asyncio
from pathlib import Path

import gdown  # type: ignore[import-untyped]


class GoogleDriveFolderDownloader:
    """Baixa documentos apenas quando o comando de aquisição é executado."""

    def __init__(self, folder_url: str, output_directory: Path) -> None:
        if not folder_url.startswith("https://drive.google.com/"):
            raise ValueError("folder_url deve apontar para o Google Drive")
        self._folder_url = folder_url
        self._output_directory = output_directory

    async def download(self) -> tuple[Path, ...]:
        return await asyncio.to_thread(self._download_sync)

    def _download_sync(self) -> tuple[Path, ...]:
        self._output_directory.mkdir(parents=True, exist_ok=True)
        downloaded = gdown.download_folder(
            url=self._folder_url,
            output=str(self._output_directory),
            quiet=False,
            use_cookies=False,
            remaining_ok=True,
        )
        if downloaded is None:
            raise RuntimeError("não foi possível baixar a pasta do Google Drive")

        pdfs = tuple(
            sorted(
                Path(path)
                for path in downloaded
                if Path(path).suffix.lower() == ".pdf"
            )
        )
        if not pdfs:
            raise RuntimeError("a pasta do Google Drive não retornou PDFs")
        return pdfs
