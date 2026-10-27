"""Repositório temporário de sessões para uma única instância."""

import asyncio
from collections.abc import Callable
from time import monotonic

from chatbot.domain.models import ChatSession


class InMemorySessionRepository:
    """Armazena sessões com expiração renovada a cada salvamento."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds deve ser maior que zero")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._sessions: dict[str, tuple[ChatSession, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> ChatSession | None:
        async with self._lock:
            stored = self._sessions.get(session_id)
            if stored is None:
                return None
            session, expires_at = stored
            if expires_at <= self._clock():
                del self._sessions[session_id]
                return None
            return session

    async def save(self, session: ChatSession) -> None:
        async with self._lock:
            self._sessions[session.id] = (
                session,
                self._clock() + self._ttl_seconds,
            )

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None
