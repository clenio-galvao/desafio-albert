"""Composition root: único local que conhece todas as implementações."""

from dataclasses import dataclass

from chatbot.adapters.outbound.documents import PdfDirectorySource
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
)
from chatbot.application.prompting import GroundedPromptBuilder
from chatbot.application.retrieval import SemanticRetriever
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
        resources=(embedding, vector_store, llm),
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
