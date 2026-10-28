"""Orquestração do chat conversacional fundamentado."""

from collections.abc import AsyncGenerator

from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.application.exceptions import EmptyGenerationError, MessageTooLongError
from chatbot.application.models import ChatEvent, ChatEventType, ChatPolicy, ChatRequest
from chatbot.application.ports import LLMPort, RetrieverPort, SessionRepositoryPort
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
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._sessions = sessions
        self._models = models
        self._contextualizer = contextualizer
        self._prompt_builder = prompt_builder
        self._policy = policy

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
        prompt = self._prompt_builder.build(
            session.recent_messages(self._policy.max_session_messages),
            [item.chunk for item in retrieved],
        )
        async for token in self._llm.stream(
            model=request.model,
            messages=prompt,
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
