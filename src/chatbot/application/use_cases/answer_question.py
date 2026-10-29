"""Orquestração do chat conversacional fundamentado."""

from collections.abc import AsyncGenerator

from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.application.exceptions import EmptyGenerationError, MessageTooLongError
from chatbot.application.models import ChatEvent, ChatEventType, ChatPolicy, ChatRequest
from chatbot.application.observability import (
    NullObservability,
    SpanAttributeWriter,
    fingerprint_session,
)
from chatbot.application.ports import (
    LLMPort,
    ObservabilityPort,
    RetrieverPort,
    SessionRepositoryPort,
)
from chatbot.application.prompting import GroundedPromptBuilder
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
        prompt_builder: GroundedPromptBuilder,
        policy: ChatPolicy,
        observability: ObservabilityPort | None = None,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._sessions = sessions
        self._models = models
        self._contextualizer = contextualizer
        self._prompt_builder = prompt_builder
        self._policy = policy
        self._observability = observability or NullObservability()

    def validate(self, request: ChatRequest) -> None:
        """Executa políticas antes de o transporte iniciar o streaming."""
        self._models.ensure_supported(request.model)
        if len(request.message) > self._policy.max_message_length:
            raise MessageTooLongError(
                f"message excede o limite de {self._policy.max_message_length} caracteres"
            )

    async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
        """Recupera evidências, gera a resposta em tokens e grava o turno só ao concluir."""
        self.validate(request)
        with self._observability.start_span(
            "chat.stream",
            {
                "chat.model": request.model,
                "session.fingerprint": fingerprint_session(request.session_id),
                "retrieval.limit": self._policy.retrieval_limit,
            },
        ) as span:
            async for event in self._stream_grounded_answer(request, span):
                yield event

    async def _stream_grounded_answer(
        self,
        request: ChatRequest,
        span: SpanAttributeWriter,
    ) -> AsyncGenerator[ChatEvent, None]:
        """Recupera, gera e só então persiste o turno, anotando o span aberto."""
        user_message = Message(role=MessageRole.USER, content=request.message)
        session = await self._copy_session(request.session_id)
        retrieval_query = self._contextualizer.contextualize(
            user_message.content,
            session.messages,
        )
        retrieved = await self._retriever.search(
            retrieval_query,
            limit=self._policy.retrieval_limit,
            score_threshold=self._policy.score_threshold,
        )
        session.add(user_message)
        citations = tuple(item.chunk.as_citation() for item in retrieved)
        best_score = max((item.score for item in retrieved), default=None)
        self._annotate_retrieval(span, citation_count=len(citations), best_score=best_score)
        yield ChatEvent(
            type=ChatEventType.METADATA,
            citations=citations,
            best_score=best_score,
        )

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
        prompt = self._prompt_builder.build(
            session.recent_messages(self._policy.max_session_messages),
            [item.chunk for item in retrieved],
        )
        with self._observability.start_span("llm", {"chat.model": request.model}):
            async for token in self._llm.stream(model=request.model, messages=prompt):
                if token:
                    response_parts.append(token)
                    yield ChatEvent(type=ChatEventType.TOKEN, content=token)

        response = "".join(response_parts).strip()
        if not response:
            raise EmptyGenerationError("o modelo não produziu conteúdo")

        session.add(Message(role=MessageRole.ASSISTANT, content=response))
        await self._sessions.save(session)
        yield ChatEvent(type=ChatEventType.DONE)

    def _annotate_retrieval(
        self,
        span: SpanAttributeWriter,
        *,
        citation_count: int,
        best_score: float | None,
    ) -> None:
        """Anota recusa e score no intervalo, sem copiar texto recuperado."""
        span.set_attribute("chat.refused", citation_count == 0)
        span.set_attribute("retrieval.citation_count", citation_count)
        if best_score is not None:
            span.set_attribute("retrieval.best_score", best_score)

    async def _copy_session(self, session_id: str) -> ChatSession:
        """Trabalha sobre uma cópia isolada para não vazar estado entre turnos."""
        existing = await self._sessions.get(session_id)
        if existing is None:
            return ChatSession(
                id=session_id,
                max_messages=self._policy.max_session_messages,
            )
        return ChatSession(
            id=existing.id,
            max_messages=self._policy.max_session_messages,
            messages=list(existing.messages[-self._policy.max_session_messages :]),
            updated_at=existing.updated_at,
        )
