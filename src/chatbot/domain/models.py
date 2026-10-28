"""Entidades e value objects independentes de infraestrutura."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from chatbot.domain.exceptions import (
    EmptyContentError,
    InvalidChunkPositionError,
    InvalidPageError,
    SessionLimitError,
)


class MessageRole(StrEnum):
    """Papéis aceitos no histórico conversacional."""

    USER = "user"
    ASSISTANT = "assistant"


def _required_text(value: str, field_name: str) -> str:
    """Remove espaços e recusa campos que ficariam vazios após a normalização."""
    normalized = value.strip()
    if not normalized:
        raise EmptyContentError(f"{field_name} não pode ser vazio")
    return normalized


@dataclass(frozen=True, slots=True)
class Message:
    """Uma mensagem validada do histórico."""

    role: MessageRole
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Garante conteúdo útil sem alterar o restante da mensagem."""
        object.__setattr__(self, "content", _required_text(self.content, "content"))


@dataclass(frozen=True, slots=True)
class Citation:
    """Referência verificável para uma página da base."""

    source: str
    title: str
    page: int
    chunk_id: str

    def __post_init__(self) -> None:
        """Normaliza identificadores e recusa página menor que 1."""
        object.__setattr__(self, "source", _required_text(self.source, "source"))
        object.__setattr__(self, "title", _required_text(self.title, "title"))
        object.__setattr__(self, "chunk_id", _required_text(self.chunk_id, "chunk_id"))
        if self.page < 1:
            raise InvalidPageError("page deve ser maior ou igual a 1")


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    """Trecho indexável com rastreabilidade até o documento original."""

    id: str
    text: str
    source: str
    title: str
    page: int
    content_hash: str
    position: int = 0

    def __post_init__(self) -> None:
        """Normaliza texto rastreável e valida página e posição na página."""
        for name in ("id", "text", "source", "title", "content_hash"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if self.page < 1:
            raise InvalidPageError("page deve ser maior ou igual a 1")
        if self.position < 0:
            raise InvalidChunkPositionError("position não pode ser negativa")

    def as_citation(self) -> Citation:
        """Produz a referência pública usada na resposta do chat."""
        return Citation(
            source=self.source,
            title=self.title,
            page=self.page,
            chunk_id=self.id,
        )


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """Trecho recuperado acompanhado da similaridade calculada."""

    chunk: DocumentChunk
    score: float

    def __post_init__(self) -> None:
        """Mantém o score de similaridade no intervalo unitário."""
        if not 0 <= self.score <= 1:
            raise ValueError("score deve estar entre 0 e 1")


@dataclass(slots=True)
class ChatSession:
    """Histórico temporário limitado para impedir crescimento indefinido."""

    id: str
    max_messages: int
    messages: list[Message] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Valida identificador, teto de mensagens e histórico inicial."""
        self.id = _required_text(self.id, "id")
        if self.max_messages < 2:
            raise ValueError("max_messages deve ser maior ou igual a 2")
        if len(self.messages) > self.max_messages:
            raise SessionLimitError("histórico inicial excede max_messages")

    def add(self, message: Message) -> None:
        """Adiciona uma mensagem e mantém apenas a janela mais recente."""
        self.messages.append(message)
        overflow = len(self.messages) - self.max_messages
        if overflow > 0:
            del self.messages[:overflow]
        self.updated_at = datetime.now(UTC)

    def recent_messages(self, limit: int) -> tuple[Message, ...]:
        """Retorna uma cópia imutável dos últimos turnos."""
        if limit < 1:
            raise ValueError("limit deve ser maior ou igual a 1")
        return tuple(self.messages[-limit:])

    def copy(self) -> "ChatSession":
        """Devolve uma sessão independente, com as mesmas mensagens."""
        return ChatSession(
            id=self.id,
            max_messages=self.max_messages,
            messages=list(self.messages),
            updated_at=self.updated_at,
        )
