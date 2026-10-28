"""Transformação determinística de páginas em trechos indexáveis."""

from collections.abc import Sequence
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from chatbot.application.models import SourcePage
from chatbot.application.ports import TokenEncodingPort
from chatbot.domain.models import DocumentChunk


class TokenChunker:
    """Divide páginas por tokens com sobreposição configurável."""

    def __init__(
        self,
        *,
        chunk_size: int,
        overlap: int,
        encoding: TokenEncodingPort,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size deve ser maior que zero")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap deve estar entre zero e chunk_size - 1")
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._encoding = encoding

    def split(self, pages: Sequence[SourcePage]) -> tuple[DocumentChunk, ...]:
        """Gera trechos determinísticos com id, hash e posição estáveis por página."""
        chunks: list[DocumentChunk] = []
        for page in pages:
            chunks.extend(self._split_page(page))
        return tuple(chunks)

    def _split_page(self, page: SourcePage) -> list[DocumentChunk]:
        """Percorre a página em janelas com sobreposição e posição local."""
        tokens = self._encoding.encode(page.text)
        step = self._chunk_size - self._overlap
        chunks: list[DocumentChunk] = []
        position = 0
        for start in range(0, len(tokens), step):
            text = self._encoding.decode(tokens[start : start + self._chunk_size]).strip()
            if text:
                chunks.append(self._chunk_from_window(page, text, start, position))
                position += 1
            if start + self._chunk_size >= len(tokens):
                break
        return chunks

    def _chunk_from_window(
        self,
        page: SourcePage,
        text: str,
        start: int,
        position: int,
    ) -> DocumentChunk:
        """Identifica o trecho pelo conteúdo e pela origem da página."""
        identity = f"{page.source}:{page.page}:{start}:{text}"
        content_hash = sha256(identity.encode("utf-8")).hexdigest()
        return DocumentChunk(
            id=str(uuid5(NAMESPACE_URL, content_hash)),
            text=text,
            source=page.source,
            title=page.title,
            page=page.page,
            content_hash=content_hash,
            position=position,
        )
