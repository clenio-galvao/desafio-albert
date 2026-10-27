"""Orquestração do chat conversacional fundamentado."""

from collections.abc import AsyncIterator

from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.application.exceptions import EmptyGenerationError
from chatbot.application.models import ChatEvent, ChatEventType, ChatRequest
from chatbot.application.ports import LLMPort, RetrieverPort, SessionRepositoryPort
from chatbot.application.use_cases.list_models import ModelCatalog
from chatbot.domain.models import ChatSession, Message, MessageRole

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "Não encontrei informação suficiente nas apostilas para responder com segurança."
)


class GroundedChatService:
    """Recupera evidências antes de gerar e mantém uma janela de conversa."""

    def __init__(
        self,
        *,
        llm: LLMPort,
        retriever: RetrieverPort,
        sessions: SessionRepositoryPort,
        models: ModelCatalog,
        contextualizer: RecentHistoryContextualizer,
        max_session_messages: int = 12,
        retrieval_limit: int = 5,
        score_threshold: float = 0.7,
    ) -> None:
        if max_session_messages < 2:
            raise ValueError("max_session_messages deve ser maior ou igual a 2")
        if retrieval_limit < 1:
            raise ValueError("retrieval_limit deve ser maior que zero")
        if not 0 <= score_threshold <= 1:
            raise ValueError("score_threshold deve estar entre 0 e 1")
        self._llm = llm
        self._retriever = retriever
        self._sessions = sessions
        self._models = models
        self._contextualizer = contextualizer
        self._max_session_messages = max_session_messages
        self._retrieval_limit = retrieval_limit
        self._score_threshold = score_threshold

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self._models.ensure_supported(request.model)
        user_message = Message(role=MessageRole.USER, content=request.message)
        session = await self._session_copy(request.session_id)
        retrieval_query = self._contextualizer.contextualize(
            user_message.content,
            session.messages,
        )
        retrieved = await self._retriever.search(
            retrieval_query,
            limit=self._retrieval_limit,
            score_threshold=self._score_threshold,
        )
        session.add(user_message)

        citations = tuple(item.chunk.citation() for item in retrieved)
        yield ChatEvent(type=ChatEventType.METADATA, citations=citations)

        if not retrieved:
            yield ChatEvent(type=ChatEventType.TOKEN, content=INSUFFICIENT_EVIDENCE_MESSAGE)
            session.add(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=INSUFFICIENT_EVIDENCE_MESSAGE,
                )
            )
            await self._sessions.save(session)
            yield ChatEvent(type=ChatEventType.DONE)
            return

        response_parts: list[str] = []
        async for token in self._llm.stream(
            model=request.model,
            messages=session.recent(self._max_session_messages),
            context=[item.chunk for item in retrieved],
        ):
            if token:
                response_parts.append(token)
                yield ChatEvent(type=ChatEventType.TOKEN, content=token)

        response = "".join(response_parts).strip()
        if not response:
            raise EmptyGenerationError("o modelo não produziu conteúdo")

        session.add(Message(role=MessageRole.ASSISTANT, content=response))
        await self._sessions.save(session)
        yield ChatEvent(type=ChatEventType.DONE)

    async def _session_copy(self, session_id: str) -> ChatSession:
        existing = await self._sessions.get(session_id)
        if existing is None:
            return ChatSession(id=session_id, max_messages=self._max_session_messages)
        return ChatSession(
            id=existing.id,
            max_messages=self._max_session_messages,
            messages=list(existing.messages[-self._max_session_messages :]),
            updated_at=existing.updated_at,
        )
