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
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class PromptMessage:
    role: PromptRole
    content: str


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
