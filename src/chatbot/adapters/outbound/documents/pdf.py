"""Leitura local de PDFs mantendo a rastreabilidade por página."""

import asyncio
import re
from collections.abc import Sequence
from pathlib import Path

from pypdf import PdfReader

from chatbot.application.models import SourcePage

_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_page_text(text: str) -> str:
    """Remove ruído comum sem destruir divisões úteis de parágrafo."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(?<=\w)-\n(?=\w)", "", normalized)
    lines = (_WHITESPACE.sub(" ", line).strip() for line in normalized.splitlines())
    normalized = "\n".join(lines)
    normalized = _BLANK_LINES.sub("\n\n", normalized)
    return normalized.strip()


class PdfDirectorySource:
    """Carrega, em ordem estável, todos os PDFs de um diretório privado."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def load(self) -> Sequence[SourcePage]:
        return await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> tuple[SourcePage, ...]:
        if not self._directory.is_dir():
            raise FileNotFoundError(f"diretório de documentos não encontrado: {self._directory}")

        pdf_paths = tuple(sorted(self._directory.glob("*.pdf")))
        if not pdf_paths:
            raise FileNotFoundError(f"nenhum PDF encontrado em: {self._directory}")

        pages: list[SourcePage] = []
        for path in pdf_paths:
            reader = PdfReader(path)
            for page_number, page in enumerate(reader.pages, start=1):
                text = normalize_page_text(page.extract_text() or "")
                if text:
                    pages.append(SourcePage(source=path.name, page=page_number, text=text))

        if not pages:
            raise ValueError("os PDFs não possuem texto extraível")
        return tuple(pages)
