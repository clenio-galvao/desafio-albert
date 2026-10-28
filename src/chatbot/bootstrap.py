"""Composition root: único local que conhece todas as implementações."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from chatbot.adapters.outbound.documents import PdfDirectorySource
from chatbot.adapters.outbound.load_doubles import AlwaysReady, LoadLLM, LoadRetriever
from chatbot.adapters.outbound.memory_sessions import InMemorySessionRepository
from chatbot.adapters.outbound.openai_compatible import (
    OpenAIChatAdapter,
    OpenAIEmbeddingAdapter,
)
from chatbot.adapters.outbound.qdrant import QdrantVectorStore
from chatbot.adapters.outbound.tiktoken_encoding import TiktokenEncoding
from chatbot.application.chunking import TokenChunker
from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.application.ports import (
    AnswerQuestion,
    AsyncClosePort,
    CheckReadiness,
    EndSession,
    IngestKnowledgeBase,
    ListModels,
    StreamGate,
)
from chatbot.application.prompting import GroundedPromptBuilder
from chatbot.application.retrieval import SemanticRetriever
from chatbot.application.stream_gate import ConcurrentStreamGate, UnlimitedStreamGate
from chatbot.application.use_cases import (
    EndSessionService,
    GroundedChatService,
    IngestionService,
    ModelCatalog,
    ReadinessService,
)
from chatbot.config import Settings


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Dependências disponibilizadas aos adapters de entrada."""

    chat: AnswerQuestion
    models: ListModels
    end_session: EndSession
    readiness: CheckReadiness
    stream_gate: StreamGate = field(default_factory=UnlimitedStreamGate)
    stream_timeout_seconds: float = 60.0
    resources: tuple[AsyncClosePort, ...] = ()

    async def close(self) -> None:
        for resource in reversed(self.resources):
            await resource.close()


@dataclass(frozen=True, slots=True)
class IngestionContainer:
    """Grafo da ingestão com encerramento uniforme dos recursos."""

    ingestion: IngestKnowledgeBase
    resources: tuple[AsyncClosePort, ...]

    async def close(self) -> None:
        for resource in reversed(self.resources):
            await resource.close()


def build_container(settings: Settings) -> ApplicationContainer:
    """Monta o grafo real sem service locator dentro dos casos de uso."""
    embedding = OpenAIEmbeddingAdapter(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
        collection_name=settings.qdrant_collection,
    )
    retriever = SemanticRetriever(
        embedding=embedding,
        index=vector_store,
        following_pages=settings.retrieval_following_pages,
    )
    llm = OpenAIChatAdapter(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    sessions = InMemorySessionRepository(
        ttl_seconds=settings.session_ttl_seconds,
        max_sessions=settings.session_max_count,
    )
    models = ModelCatalog(settings.allowed_chat_models)
    chat = GroundedChatService(
        llm=llm,
        retriever=retriever,
        sessions=sessions,
        models=models,
        contextualizer=RecentHistoryContextualizer(
            max_history_messages=settings.retrieval_history_messages
        ),
        prompt_builder=GroundedPromptBuilder(),
        max_session_messages=settings.session_max_messages,
        retrieval_limit=settings.retrieval_top_k,
        score_threshold=settings.retrieval_score_threshold,
        max_message_length=settings.max_message_length,
    )
    return ApplicationContainer(
        chat=chat,
        models=models,
        end_session=EndSessionService(sessions),
        readiness=ReadinessService(vector_store),
        stream_gate=ConcurrentStreamGate(settings.max_concurrent_streams),
        stream_timeout_seconds=settings.stream_timeout_seconds,
        resources=(embedding, vector_store, llm),
    )


def build_load_container(
    *,
    models: Sequence[str] = ("azure/gpt-5-mini", "azure/gpt-6-luna"),
    token_delay_seconds: float = 0.005,
    max_concurrent_streams: int = 10_000,
    stream_timeout_seconds: float = 60.0,
) -> ApplicationContainer:
    """Monta a API com dublês para teste de carga sem cota externa."""
    sessions = InMemorySessionRepository(ttl_seconds=3600, max_sessions=10_000)
    catalog = ModelCatalog(tuple(models))
    chat = GroundedChatService(
        llm=LoadLLM(delay_seconds=token_delay_seconds),
        retriever=LoadRetriever(),
        sessions=sessions,
        models=catalog,
        contextualizer=RecentHistoryContextualizer(max_history_messages=4),
        prompt_builder=GroundedPromptBuilder(),
        max_session_messages=12,
        retrieval_limit=3,
        score_threshold=0.35,
        max_message_length=4000,
    )
    return ApplicationContainer(
        chat=chat,
        models=catalog,
        end_session=EndSessionService(sessions),
        readiness=ReadinessService(AlwaysReady()),
        stream_gate=ConcurrentStreamGate(max_concurrent_streams),
        stream_timeout_seconds=stream_timeout_seconds,
    )


def build_ingestion(settings: Settings) -> IngestionContainer:
    """Monta a ingestão sem duplicar composição no entrypoint CLI."""
    embedding = OpenAIEmbeddingAdapter(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
        collection_name=settings.qdrant_collection,
    )
    ingestion = IngestionService(
        source=PdfDirectorySource(settings.documents_dir),
        chunker=TokenChunker(
            chunk_size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
            encoding=TiktokenEncoding(),
        ),
        embedding=embedding,
        vector_store=vector_store,
    )
    return IngestionContainer(
        ingestion=ingestion,
        resources=(embedding, vector_store),
    )
