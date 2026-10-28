"""Contextualização econômica de consultas sem uma segunda chamada ao LLM."""

import re
from collections.abc import Sequence

from chatbot.domain.models import Message

_HISTORY_REFERENCE = re.compile(
    r"^(?:e|mas|então)\b|"
    r"\b(?:isso|isto|aquilo|ele|ela|eles|elas|esse|essa|esses|essas|"
    r"anterior|acima)\b",
    re.IGNORECASE,
)
_VAGUE_FOLLOW_UP = re.compile(
    r"^(?:como|por que|quando|onde)\s+"
    r"(?:funciona|acontece|ocorre|fazer|tratar)\??$",
    re.IGNORECASE,
)


class RecentHistoryContextualizer:
    """Combina a pergunta atual somente com a janela recente da conversa."""

    def __init__(self, max_history_messages: int = 4) -> None:
        if max_history_messages < 0:
            raise ValueError("max_history_messages não pode ser negativo")
        self._max_history_messages = max_history_messages

    def contextualize(self, question: str, history: Sequence[Message]) -> str:
        """Anexa histórico recente só quando a pergunta depende do contexto."""
        if self._max_history_messages == 0 or not history:
            return question
        normalized = " ".join(question.split())
        if not (
            _HISTORY_REFERENCE.search(normalized)
            or _VAGUE_FOLLOW_UP.fullmatch(normalized)
        ):
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
