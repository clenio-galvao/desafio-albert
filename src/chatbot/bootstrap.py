"""Composition root: único local que conhece todas as implementações."""

from dataclasses import dataclass

from chatbot.adapters.outbound.memory_sessions import InMemorySessionRepository
from chatbot.adapters.outbound.openai_compatible import (
    OpenAIChatAdapter,
    OpenAIEmbeddingAdapter,
)
from chatbot.adapters.outbound.qdrant import QdrantVectorStore
from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.application.ports import (
    AnswerQuestion,
    AsyncClosePort,
    ReadinessPort,
    SessionRepositoryPort,
)
from chatbot.application.use_cases import GroundedChatService, ModelCatalog
from chatbot.config import Settings


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Dependências disponibilizadas aos adapters de entrada."""

    chat: AnswerQuestion
    models: ModelCatalog
    sessions: SessionRepositoryPort
    readiness: ReadinessPort
    resources: tuple[AsyncClosePort, ...] = ()
    max_message_length: int = 4000

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
        embedding=embedding,
    )
    llm = OpenAIChatAdapter(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    sessions = InMemorySessionRepository(ttl_seconds=settings.session_ttl_seconds)
    models = ModelCatalog(settings.allowed_chat_models)
    chat = GroundedChatService(
        llm=llm,
        retriever=vector_store,
        sessions=sessions,
        models=models,
        contextualizer=RecentHistoryContextualizer(
            max_history_messages=settings.retrieval_history_messages
        ),
        max_session_messages=settings.session_max_messages,
        retrieval_limit=settings.retrieval_top_k,
        score_threshold=settings.retrieval_score_threshold,
    )
    return ApplicationContainer(
        chat=chat,
        models=models,
        sessions=sessions,
        readiness=vector_store,
        resources=(embedding, vector_store, llm),
        max_message_length=settings.max_message_length,
    )
