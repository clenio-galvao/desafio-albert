"""Portas que isolam casos de uso de frameworks e serviços externos."""

from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from typing import Protocol

from chatbot.application.models import (
    ChatEvent,
    ChatRequest,
    IngestionResult,
    PromptMessage,
    SourcePage,
)
from chatbot.domain.models import ChatSession, DocumentChunk, RetrievedChunk


class LLMPort(Protocol):
    """Geração de texto por qualquer modelo compatível."""

    def stream(
        self,
        *,
        model: str,
        messages: Sequence[PromptMessage],
    ) -> AsyncIterator[str]: ...


class EmbeddingPort(Protocol):
    """Geração vetorial em lote."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class TokenEncodingPort(Protocol):
    """Codificação de texto injetada no chunking."""

    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: Sequence[int]) -> str: ...


class RetrieverPort(Protocol):
    """Busca semântica na base de conhecimento."""

    async def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]: ...


class VectorIndexPort(Protocol):
    """Índice vetorial sem decisões de embedding ou expansão."""

    async def query(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]: ...

    async def pages_after(
        self,
        chunk: DocumentChunk,
        count: int,
    ) -> Sequence[DocumentChunk]:
        """Retorna o primeiro trecho de cada uma das `count` páginas seguintes, em ordem."""
        ...


class VectorStorePort(Protocol):
    """Persistência vetorial usada pela ingestão."""

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


class StreamGate(Protocol):
    """Admissão de streams simultâneos antes de o SSE começar."""

    async def try_acquire(self) -> bool: ...

    async def release(self) -> None: ...


class ApplicationServices(Protocol):
    """Fachada de portas de entrada disponibilizada aos adapters."""

    @property
    def chat(self) -> AnswerQuestion: ...

    @property
    def models(self) -> ListModels: ...

    @property
    def end_session(self) -> EndSession: ...

    @property
    def readiness(self) -> CheckReadiness: ...

    @property
    def stream_gate(self) -> StreamGate: ...

    @property
    def stream_timeout_seconds(self) -> float: ...
