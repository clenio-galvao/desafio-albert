"""Contextualização econômica de consultas sem uma segunda chamada ao LLM."""

from collections.abc import Sequence

from chatbot.domain.models import Message


class RecentHistoryContextualizer:
    """Combina a pergunta atual somente com a janela recente da conversa."""

    def __init__(self, max_history_messages: int = 4) -> None:
        if max_history_messages < 0:
            raise ValueError("max_history_messages não pode ser negativo")
        self._max_history_messages = max_history_messages

    def contextualize(self, question: str, history: Sequence[Message]) -> str:
        if self._max_history_messages == 0 or not history:
            return question

        recent = history[-self._max_history_messages :]
        lines = [f"{message.role.value}: {message.content}" for message in recent]
        return "\n".join(
            [
                "Contexto recente da conversa:",
                *lines,
                f"Pergunta atual: {question}",
            ]
        )
