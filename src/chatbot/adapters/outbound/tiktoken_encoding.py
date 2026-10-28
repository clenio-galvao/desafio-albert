"""Codificação de tokens baseada em tiktoken."""

from collections.abc import Sequence

import tiktoken


class TiktokenEncoding:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding = tiktoken.get_encoding(encoding_name)

    def encode(self, text: str) -> list[int]:
        return self._encoding.encode(text)

    def decode(self, tokens: Sequence[int]) -> str:
        return self._encoding.decode(tokens)
