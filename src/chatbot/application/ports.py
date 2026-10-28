"""Portas que isolam casos de uso de frameworks e serviços externos."""

from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from typing import Protocol

from chatbot.application.models import ChatEvent, ChatRequest, IngestionResult, SourcePage
from chatbot.domain.models import ChatSession, DocumentChunk, Message, RetrievedChunk


class LLMPort(Protocol):
    """Geração de texto por qualquer modelo compatível."""

    def stream(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        context: Sequence[DocumentChunk],
    ) -> AsyncIterator[str]: ...


class EmbeddingPort(Protocol):
    """Geração vetorial em lote."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class RetrieverPort(Protocol):
    """Busca semântica na base de conhecimento."""

    async def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]: ...


class VectorStorePort(RetrieverPort, Protocol):
    """Persistência usada pela ingestão e pela recuperação."""

    async def ensure_indexes(self) -> None: ...

    async def existing_hashes(self, hashes: Sequence[str]) -> set[str]: ...

    async def upsert(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None: ...


class SessionRepositoryPort(Protocol):
    """Armazenamento substituível do histórico conversacional."""

    async def get(self, session_id: str) -> ChatSession | None: ...

    async def save(self, session: ChatSession) -> None: ...

    async def delete(self, session_id: str) -> bool: ...


class DocumentSourcePort(Protocol):
    """Origem abstrata das páginas a serem indexadas."""

    async def load(self) -> Sequence[SourcePage]: ...


class AnswerQuestion(Protocol):
    """Porta de entrada do chat em streaming."""

    def validate(self, request: ChatRequest) -> None: ...

    def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]: ...


class EndSession(Protocol):
    """Porta de entrada para encerrar uma conversa."""

    async def execute(self, session_id: str) -> bool: ...


class CheckReadiness(Protocol):
    """Porta de entrada para verificar dependências da aplicação."""

    async def execute(self) -> bool: ...


class IngestKnowledgeBase(Protocol):
    """Porta de entrada da indexação."""

    async def execute(self) -> IngestionResult: ...


class ListModels(Protocol):
    """Porta de entrada da descoberta de modelos permitidos."""

    def execute(self) -> tuple[str, ...]: ...


class ReadinessPort(Protocol):
    """Verificação da dependência necessária para servir o RAG."""

    async def ready(self) -> bool: ...


class AsyncClosePort(Protocol):
    """Recurso assíncrono encerrado no ciclo de vida da aplicação."""

    async def close(self) -> None: ...
