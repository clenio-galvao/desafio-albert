"""Caso de uso para encerrar uma sessão de conversa."""

from chatbot.application.ports import SessionRepositoryPort


class EndSessionService:
    """Remove o histórico sem expor o repositório ao adapter de entrada."""

    def __init__(self, sessions: SessionRepositoryPort) -> None:
        self._sessions = sessions

    async def execute(self, session_id: str) -> bool:
        """Apaga o histórico e informa se a sessão existia."""
        return await self._sessions.delete(session_id)
