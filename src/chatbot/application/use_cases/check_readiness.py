"""Caso de uso para verificar a disponibilidade das dependências."""

from chatbot.application.ports import ReadinessPort


class ReadinessService:
    """Traduz falhas da dependência em estado não pronto."""

    def __init__(self, dependency: ReadinessPort) -> None:
        self._dependency = dependency

    async def execute(self) -> bool:
        """Traduz falha da dependência em `False`, sem vazar o erro original."""
        try:
            return await self._dependency.ready()
        except Exception:
            return False
