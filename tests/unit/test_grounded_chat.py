import pytest

from chatbot.application import (
    ChatEventType,
    ChatRequest,
    EmptyGenerationError,
    UnsupportedModelError,
)
from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.application.use_cases import GroundedChatService, ModelCatalog
from chatbot.application.use_cases.answer_question import INSUFFICIENT_EVIDENCE_MESSAGE
from chatbot.domain import DocumentChunk, Message, MessageRole, RetrievedChunk

from ..fakes import FakeLLM, FakeSessionRepository, FakeVectorStore


def make_retrieved_chunk(score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=DocumentChunk(
            id="chunk-1",
            text="Atividade física pode apoiar a saúde mental.",
            source="apostila.pdf",
            page=7,
            content_hash="hash",
        ),
        score=score,
    )


def make_service(
    *,
    llm: FakeLLM | None = None,
    retriever: FakeVectorStore | None = None,
    sessions: FakeSessionRepository | None = None,
    **changes: object,
) -> GroundedChatService:
    options: dict[str, object] = {
        "llm": llm or FakeLLM(("res", "posta")),
        "retriever": retriever or FakeVectorStore([make_retrieved_chunk()]),
        "sessions": sessions or FakeSessionRepository(),
        "models": ModelCatalog(["model-a", "model-b"]),
        "contextualizer": RecentHistoryContextualizer(max_history_messages=2),
        "max_session_messages": 4,
        "retrieval_limit": 3,
        "score_threshold": 0.7,
    }
    options.update(changes)
    return GroundedChatService(**options)  # type: ignore[arg-type]


def test_contextualizer_uses_only_recent_history() -> None:
    contextualizer = RecentHistoryContextualizer(max_history_messages=2)
    history = [
        Message(MessageRole.USER, "antiga"),
        Message(MessageRole.ASSISTANT, "resposta recente"),
        Message(MessageRole.USER, "pergunta recente"),
    ]

    query = contextualizer.contextualize("e agora?", history)

    assert "antiga" not in query
    assert "assistant: resposta recente" in query
    assert query.endswith("Pergunta atual: e agora?")
    assert RecentHistoryContextualizer(0).contextualize("direta", history) == "direta"
    assert contextualizer.contextualize("direta", []) == "direta"
    assert (
        contextualizer.contextualize("O que é escuta terapêutica?", history)
        == "O que é escuta terapêutica?"
    )
    assert "Contexto recente" in contextualizer.contextualize("Como funciona?", history)


def test_contextualizer_rejects_negative_history_limit() -> None:
    with pytest.raises(ValueError, match="max_history_messages"):
        RecentHistoryContextualizer(-1)


def test_grounded_chat_validates_configuration() -> None:
    with pytest.raises(ValueError, match="max_session_messages"):
        make_service(max_session_messages=1)
    with pytest.raises(ValueError, match="retrieval_limit"):
        make_service(retrieval_limit=0)
    with pytest.raises(ValueError, match="score_threshold"):
        make_service(score_threshold=-0.1)
    with pytest.raises(ValueError, match="score_threshold"):
        make_service(score_threshold=1.1)


async def test_grounded_chat_streams_answer_with_citations_and_saves_history() -> None:
    llm = FakeLLM(("res", "posta"))
    sessions = FakeSessionRepository()
    service = make_service(llm=llm, sessions=sessions)
    request = ChatRequest(session_id="session", message="Como cuidar?", model="model-a")

    events = [event async for event in service.stream(request)]

    assert [event.type for event in events] == [
        ChatEventType.METADATA,
        ChatEventType.TOKEN,
        ChatEventType.TOKEN,
        ChatEventType.DONE,
    ]
    assert events[0].citations[0].page == 7
    assert "".join(event.content or "" for event in events) == "resposta"
    assert llm.models == ["model-a"]
    assert llm.contexts[0][0].source == "apostila.pdf"
    assert [message.content for message in sessions.sessions["session"].messages] == [
        "Como cuidar?",
        "resposta",
    ]


async def test_grounded_chat_refuses_without_evidence_and_skips_llm() -> None:
    llm = FakeLLM()
    sessions = FakeSessionRepository()
    service = make_service(
        llm=llm,
        sessions=sessions,
        retriever=FakeVectorStore(),
    )

    events = [
        event
        async for event in service.stream(
            ChatRequest(session_id="session", message="Sem resposta?", model="model-a")
        )
    ]

    assert events[0].citations == ()
    assert events[1].content == INSUFFICIENT_EVIDENCE_MESSAGE
    assert events[-1].type is ChatEventType.DONE
    assert llm.models == []
    assert sessions.sessions["session"].messages[-1].content == INSUFFICIENT_EVIDENCE_MESSAGE


async def test_grounded_chat_contextualizes_follow_up_from_existing_session() -> None:
    sessions = FakeSessionRepository()
    retriever = FakeVectorStore([make_retrieved_chunk()])
    service = make_service(sessions=sessions, retriever=retriever)
    first = ChatRequest(session_id="session", message="O que ajuda?", model="model-a")
    second = ChatRequest(session_id="session", message="E com que frequência?", model="model-a")

    _ = [event async for event in service.stream(first)]
    _ = [event async for event in service.stream(second)]

    assert retriever.queries[0] == "O que ajuda?"
    assert "assistant: resposta" in retriever.queries[1]
    assert retriever.queries[1].endswith("Pergunta atual: E com que frequência?")
    assert len(sessions.sessions["session"].messages) == 4


async def test_grounded_chat_rejects_model_before_retrieval() -> None:
    retriever = FakeVectorStore([make_retrieved_chunk()])
    service = make_service(retriever=retriever)

    with pytest.raises(UnsupportedModelError):
        _ = [
            event
            async for event in service.stream(
                ChatRequest(session_id="session", message="pergunta", model="unknown")
            )
        ]

    assert retriever.queries == []


async def test_grounded_chat_rejects_empty_model_stream_without_saving() -> None:
    sessions = FakeSessionRepository()
    service = make_service(llm=FakeLLM(("", "   ")), sessions=sessions)

    with pytest.raises(EmptyGenerationError):
        _ = [
            event
            async for event in service.stream(
                ChatRequest(session_id="session", message="pergunta", model="model-a")
            )
        ]

    assert sessions.sessions == {}
