"""Núcleo de domínio do chatbot."""

from chatbot.domain.exceptions import (
    DomainError,
    EmptyContentError,
    InvalidChunkPositionError,
    InvalidPageError,
    SessionLimitError,
)
from chatbot.domain.models import (
    ChatSession,
    Citation,
    DocumentChunk,
    Message,
    MessageRole,
    RetrievedChunk,
)

__all__ = [
    "ChatSession",
    "Citation",
    "DocumentChunk",
    "DomainError",
    "EmptyContentError",
    "InvalidChunkPositionError",
    "InvalidPageError",
    "Message",
    "MessageRole",
    "RetrievedChunk",
    "SessionLimitError",
]
