"""Modelos de entrada e saída dos casos de uso."""

from dataclasses import dataclass, field
from enum import StrEnum

from chatbot.domain.models import Citation


class ChatEventType(StrEnum):
    """Tipos estáveis emitidos pelo streaming da aplicação."""

    METADATA = "metadata"
    TOKEN = "token"
    DONE = "done"


class PromptRole(StrEnum):
    """Papéis do prompt enviado ao modelo."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class PromptMessage:
    role: PromptRole
    content: str


@dataclass(frozen=True, slots=True)
class ChatPolicy:
    """Números de recuperação, sessão e mensagem usados pelo chat."""

    max_session_messages: int
    retrieval_limit: int
    score_threshold: float
    max_message_length: int

    def __post_init__(self) -> None:
        """Recusa combinações que tornariam o RAG ou a sessão inválidos."""
        if self.max_session_messages < 2:
            raise ValueError("max_session_messages deve ser maior ou igual a 2")
        if self.retrieval_limit < 1:
            raise ValueError("retrieval_limit deve ser maior que zero")
        if not 0 <= self.score_threshold <= 1:
            raise ValueError("score_threshold deve estar entre 0 e 1")
        if self.max_message_length < 1:
            raise ValueError("max_message_length deve ser maior que zero")


@dataclass(frozen=True, slots=True)
class ChatRequest:
    session_id: str
    message: str
    model: str


@dataclass(frozen=True, slots=True)
class ChatEvent:
    type: ChatEventType
    content: str | None = None
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    best_score: float | None = None


@dataclass(frozen=True, slots=True)
class SourcePage:
    source: str
    title: str
    page: int
    text: str


@dataclass(frozen=True, slots=True)
class IngestionResult:
    documents: int
    chunks: int
    embedded_chunks: int
    skipped_chunks: int
