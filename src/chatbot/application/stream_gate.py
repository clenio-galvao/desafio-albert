"""Controle de admissão de streams SSE antes de abrir o canal."""

import asyncio


class UnlimitedStreamGate:
    """Permite qualquer quantidade de streams; usado em testes isolados."""

    async def try_acquire(self) -> bool:
        """Sempre admite o stream, para testes sem teto de concorrência."""
        return True

    async def release(self) -> None:
        """Não altera estado; existe para honrar o contrato da porta."""
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
        """Quantidade de streams atualmente admitidos."""
        return self._active

    @property
    def limit(self) -> int:
        """Teto de streams admitidos ao mesmo tempo."""
        return self._limit

    async def try_acquire(self) -> bool:
        """Reserva uma vaga se o limite ainda não foi atingido."""
        async with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        """Devolve uma vaga sem deixar o contador negativo."""
        async with self._lock:
            if self._active:
                self._active -= 1
