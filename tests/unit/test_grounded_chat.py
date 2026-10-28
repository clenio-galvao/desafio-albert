import pytest

from chatbot.application import (
    ChatEventType,
    ChatRequest,
    EmptyGenerationError,
    MessageTooLongError,
    UnsupportedModelError,
)
from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.application.prompting import GroundedPromptBuilder
from chatbot.application.use_cases import GroundedChatService, ModelCatalog
from chatbot.application.use_cases.answer_question import INSUFFICIENT_EVIDENCE_MESSAGE
from chatbot.domain import DocumentChunk, RetrievedChunk

from ..fakes import FakeLLM, FakeSessionRepository, FakeVectorStore


def make_retrieved_chunk(score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=DocumentChunk(
            id="chunk-1",
            text="Atividade física pode apoiar a saúde mental.",
            source="apostila.pdf",
            title="Apostila",
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
        "prompt_builder": GroundedPromptBuilder(),
        "max_session_messages": 4,
        "retrieval_limit": 3,
        "score_threshold": 0.7,
    }
    options.update(changes)
    return GroundedChatService(**options)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"max_session_messages": 1}, "max_session_messages"),
        ({"retrieval_limit": 0}, "retrieval_limit"),
        ({"score_threshold": -0.1}, "score_threshold"),
        ({"score_threshold": 1.1}, "score_threshold"),
        ({"max_message_length": 0}, "max_message_length"),
    ],
)
def test_grounded_chat_rejects_invalid_configuration(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        make_service(**changes)  # type: ignore[arg-type]


def test_grounded_chat_preflight_rejects_long_message() -> None:
    service = make_service(max_message_length=5)

    with pytest.raises(MessageTooLongError, match="5"):
        service.validate(
            ChatRequest(session_id="session", message="muito longa", model="model-a")
        )


async def test_grounded_chat_streams_citations_then_tokens() -> None:
    events = [
        event
        async for event in make_service(llm=FakeLLM(("res", "posta"))).stream(
            ChatRequest(session_id="session", message="Como cuidar?", model="model-a")
        )
    ]

    assert [event.type for event in events] == [
        ChatEventType.METADATA,
        ChatEventType.TOKEN,
        ChatEventType.TOKEN,
        ChatEventType.DONE,
    ]
    assert events[0].citations[0].page == 7
    assert "".join(event.content or "" for event in events) == "resposta"


async def test_grounded_chat_saves_user_and_assistant_messages() -> None:
    sessions = FakeSessionRepository()
    service = make_service(llm=FakeLLM(("res", "posta")), sessions=sessions)

    _ = [
        event
        async for event in service.stream(
            ChatRequest(session_id="session", message="Como cuidar?", model="model-a")
        )
    ]

    assert [message.content for message in sessions.sessions["session"].messages] == [
        "Como cuidar?",
        "resposta",
    ]


async def test_grounded_chat_sends_selected_model_and_source_payload() -> None:
    llm = FakeLLM(("res", "posta"))
    service = make_service(llm=llm)

    _ = [
        event
        async for event in service.stream(
            ChatRequest(session_id="session", message="Como cuidar?", model="model-a")
        )
    ]

    assert llm.models == ["model-a"]
    assert '"source": "apostila.pdf"' in llm.messages[0][-1].content


async def test_grounded_chat_refuses_without_evidence() -> None:
    events = [
        event
        async for event in make_service(retriever=FakeVectorStore()).stream(
            ChatRequest(session_id="session", message="Sem resposta?", model="model-a")
        )
    ]

    assert events[0].citations == ()
    assert events[1].content == INSUFFICIENT_EVIDENCE_MESSAGE
    assert events[-1].type is ChatEventType.DONE


async def test_grounded_chat_skips_llm_without_evidence() -> None:
    llm = FakeLLM()
    service = make_service(llm=llm, retriever=FakeVectorStore())

    _ = [
        event
        async for event in service.stream(
            ChatRequest(session_id="session", message="Sem resposta?", model="model-a")
        )
    ]

    assert llm.models == []


async def test_grounded_chat_saves_refusal_in_session() -> None:
    sessions = FakeSessionRepository()
    service = make_service(sessions=sessions, retriever=FakeVectorStore())

    _ = [
        event
        async for event in service.stream(
            ChatRequest(session_id="session", message="Sem resposta?", model="model-a")
        )
    ]

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
