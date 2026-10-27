"""Transformação determinística de páginas em trechos indexáveis."""

from collections.abc import Sequence
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

import tiktoken

from chatbot.application.models import SourcePage
from chatbot.domain.models import DocumentChunk


class TokenEncoding(Protocol):
    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: Sequence[int]) -> str: ...


class TokenChunker:
    """Divide páginas por tokens com sobreposição configurável."""

    def __init__(
        self,
        *,
        chunk_size: int,
        overlap: int,
        encoding_name: str = "cl100k_base",
        encoding: TokenEncoding | None = None,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size deve ser maior que zero")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap deve estar entre zero e chunk_size - 1")
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._encoding = encoding or tiktoken.get_encoding(encoding_name)

    def split(self, pages: Sequence[SourcePage]) -> tuple[DocumentChunk, ...]:
        chunks: list[DocumentChunk] = []
        step = self._chunk_size - self._overlap

        for page in pages:
            tokens = self._encoding.encode(page.text)
            for start in range(0, len(tokens), step):
                text = self._encoding.decode(tokens[start : start + self._chunk_size]).strip()
                if not text:
                    continue
                identity = f"{page.source}:{page.page}:{start}:{text}"
                content_hash = sha256(identity.encode("utf-8")).hexdigest()
                identifier = uuid5(NAMESPACE_URL, content_hash)
                chunks.append(
                    DocumentChunk(
                        id=str(identifier),
                        text=text,
                        source=page.source,
                        page=page.page,
                        content_hash=content_hash,
                    )
                )
                if start + self._chunk_size >= len(tokens):
                    break

        return tuple(chunks)
