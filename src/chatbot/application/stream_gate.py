"""Controle de admissão de streams SSE antes de abrir o canal."""

import asyncio


class UnlimitedStreamGate:
    """Permite qualquer quantidade de streams; usado em testes isolados."""

    async def try_acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


class ConcurrentStreamGate:
    """Recusa novas respostas quando o limite de streams ativos é atingido."""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        self._limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return self._active

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            if self._active:
                self._active -= 1
