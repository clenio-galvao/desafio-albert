"""Portas que isolam casos de uso de frameworks e serviços externos."""

from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from chatbot.application.models import (
    ChatEvent,
    ChatRequest,
    IngestionResult,
    PromptMessage,
    SourcePage,
)
from chatbot.application.observability import ChatObservation, SpanAttributeWriter
from chatbot.domain.models import ChatSession, DocumentChunk, RetrievedChunk


class LLMPort(Protocol):
    """Geração de texto por qualquer modelo compatível."""

    def stream(
        self,
        *,
        model: str,
        messages: Sequence[PromptMessage],
    ) -> AsyncIterator[str]:
        """Emite tokens incrementais da resposta."""
        ...


class EmbeddingPort(Protocol):
    """Geração vetorial em lote."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Devolve um vetor para cada texto, na mesma ordem."""
        ...


class TokenEncodingPort(Protocol):
    """Codificação de texto injetada no chunking."""

    def encode(self, text: str) -> list[int]:
        """Transforma texto em tokens do encoder configurado."""
        ...

    def decode(self, tokens: Sequence[int]) -> str:
        """Reconstrói texto a partir dos tokens."""
        ...


class RetrieverPort(Protocol):
    """Busca semântica na base de conhecimento."""

    async def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Recupera trechos relevantes acima do limiar informado."""
        ...


class VectorIndexPort(Protocol):
    """Índice vetorial sem decisões de embedding ou expansão."""

    async def query(
        self,
        vector: Sequence[float],
        *,
        limit: int,
        score_threshold: float,
    ) -> Sequence[RetrievedChunk]:
        """Consulta vizinhos mais próximos a partir de um vetor pronto."""
        ...

    async def pages_after(
        self,
        chunk: DocumentChunk,
        count: int,
    ) -> Sequence[DocumentChunk]:
        """Retorna o primeiro trecho de cada uma das `count` páginas seguintes, em ordem."""
        ...


class VectorStorePort(Protocol):
    """Persistência vetorial usada pela ingestão."""

    async def ensure_indexes(self) -> None:
        """Garante os índices de payload necessários à busca e à deduplicação."""
        ...

    async def existing_hashes(self, hashes: Sequence[str]) -> set[str]:
        """Informa quais hashes já estão persistidos."""
        ...

    async def upsert(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Grava trechos e vetores correspondentes."""
        ...


class SessionRepositoryPort(Protocol):
    """Armazenamento substituível do histórico conversacional."""

    async def get(self, session_id: str) -> ChatSession | None:
        """Carrega a sessão ou indica que ela ainda não existe."""
        ...

    async def save(self, session: ChatSession) -> None:
        """Persiste uma cópia isolada da sessão."""
        ...

    async def delete(self, session_id: str) -> bool:
        """Remove a sessão e informa se ela existia."""
        ...


class DocumentSourcePort(Protocol):
    """Origem abstrata das páginas a serem indexadas."""

    async def load(self) -> Sequence[SourcePage]:
        """Lê as páginas na ordem estável da origem."""
        ...


class AnswerQuestion(Protocol):
    """Porta de entrada do chat em streaming."""

    def validate(self, request: ChatRequest) -> None:
        """Recusa a pergunta antes de abrir o canal de resposta."""
        ...

    def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
        """Gera metadados, tokens e conclusão da resposta fundamentada."""
        ...


class EndSession(Protocol):
    """Porta de entrada para encerrar uma conversa."""

    async def execute(self, session_id: str) -> bool:
        """Apaga o histórico da sessão."""
        ...


class CheckReadiness(Protocol):
    """Porta de entrada para verificar dependências da aplicação."""

    async def execute(self) -> bool:
        """Indica se a aplicação pode atender perguntas."""
        ...


class IngestKnowledgeBase(Protocol):
    """Porta de entrada da indexação."""

    async def execute(self) -> IngestionResult:
        """Indexa a base sem repetir embeddings já persistidos."""
        ...


class ListModels(Protocol):
    """Porta de entrada da descoberta de modelos permitidos."""

    def execute(self) -> tuple[str, ...]:
        """Lista os modelos aceitos pela aplicação."""
        ...


class ReadinessPort(Protocol):
    """Verificação da dependência necessária para servir o RAG."""

    async def ready(self) -> bool:
        """Confirma que a dependência externa está acessível."""
        ...


class AsyncClosePort(Protocol):
    """Recurso assíncrono encerrado no ciclo de vida da aplicação."""

    async def close(self) -> None:
        """Libera conexões e clientes associados."""
        ...


class ObservabilityPort(Protocol):
    """Telemetria do chat sem texto da conversa nem dependência de fornecedor."""

    def start_span(
        self,
        name: str,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> AbstractContextManager[SpanAttributeWriter]:
        """Abre um intervalo operacional e o fecha ao sair do bloco."""
        ...

    def record_chat(self, observation: ChatObservation) -> None:
        """Registra o desfecho de um stream sem texto da conversa."""
        ...

    def record_admission_rejected(
        self,
        *,
        request_id: str,
        session_fingerprint: str,
    ) -> None:
        """Conta um stream recusado por saturação antes do SSE."""
        ...


class StreamGate(Protocol):
    """Admissão de streams simultâneos antes de o SSE começar."""

    async def try_acquire(self) -> bool:
        """Tenta reservar uma vaga de stream ativo."""
        ...

    async def release(self) -> None:
        """Devolve a vaga ao encerrar ou falhar o stream."""
        ...


class ApplicationServices(Protocol):
    """Fachada de portas de entrada disponibilizada aos adapters."""

    @property
    def chat(self) -> AnswerQuestion:
        """Caso de uso de resposta em streaming."""
        ...

    @property
    def models(self) -> ListModels:
        """Catálogo de modelos permitidos."""
        ...

    @property
    def end_session(self) -> EndSession:
        """Encerramento de sessão conversacional."""
        ...

    @property
    def readiness(self) -> CheckReadiness:
        """Verificação das dependências do RAG."""
        ...

    @property
    def stream_gate(self) -> StreamGate:
        """Controle de concorrência dos streams SSE."""
        ...

    @property
    def stream_timeout_seconds(self) -> float:
        """Tempo máximo de uma geração; zero desativa o limite."""
        ...

    @property
    def observability(self) -> ObservabilityPort:
        """Telemetria do chat, sem texto da conversa."""
        ...
