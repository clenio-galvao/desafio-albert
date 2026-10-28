"""Codificação de tokens baseada em tiktoken."""

from collections.abc import Sequence

import tiktoken


class TiktokenEncoding:
    """Adapter fino sobre o encoder tiktoken usado no chunking."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding = tiktoken.get_encoding(encoding_name)

    def encode(self, text: str) -> list[int]:
        """Transforma texto em tokens do encoding configurado."""
        return self._encoding.encode(text)

    def decode(self, tokens: Sequence[int]) -> str:
        """Reconstrói texto a partir dos tokens."""
        return self._encoding.decode(tokens)
