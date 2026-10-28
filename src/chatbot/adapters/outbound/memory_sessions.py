"""Repositório temporário de sessões para uma única instância."""

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from time import monotonic

from chatbot.domain.models import ChatSession


def _copy(session: ChatSession) -> ChatSession:
    return ChatSession(
        id=session.id,
        max_messages=session.max_messages,
        messages=list(session.messages),
        updated_at=session.updated_at,
    )


class InMemorySessionRepository:
    """Armazena cópias de sessões com TTL renovado a cada salvamento e teto de memória."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_sessions: int = 10_000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds deve ser maior que zero")
        if max_sessions < 1:
            raise ValueError("max_sessions deve ser maior que zero")
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._clock = clock
        # Com TTL fixo e relógio monotônico, a ordem de salvamento é a ordem de expiração.
        self._sessions: OrderedDict[str, tuple[ChatSession, float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> ChatSession | None:
        async with self._lock:
            self._evict_expired()
            stored = self._sessions.get(session_id)
            return None if stored is None else _copy(stored[0])

    async def save(self, session: ChatSession) -> None:
        async with self._lock:
            self._evict_expired()
            self._sessions[session.id] = (
                _copy(session),
                self._clock() + self._ttl_seconds,
            )
            self._sessions.move_to_end(session.id)
            while len(self._sessions) > self._max_sessions:
                self._sessions.popitem(last=False)

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _evict_expired(self) -> None:
        now = self._clock()
        while self._sessions:
            oldest_id, (_, expires_at) = next(iter(self._sessions.items()))
            if expires_at > now:
                return
            del self._sessions[oldest_id]
