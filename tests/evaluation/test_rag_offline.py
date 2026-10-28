import json
from pathlib import Path
from typing import TypedDict, cast

import pytest

from chatbot.application import ChatEventType, ChatPolicy, ChatRequest
from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.application.prompting import GroundedPromptBuilder
from chatbot.application.use_cases import GroundedChatService, ModelCatalog
from chatbot.domain import DocumentChunk, RetrievedChunk
from chatbot.evaluation import ObservedCitation, evaluate_answer

from ..fakes import FakeLLM, FakeSessionRepository, FakeVectorStore


class EvaluationCase(TypedDict):
    id: str
    question: str
    setup_questions: list[str]
    answerable: bool
    expected_title: str | None
    expected_pages: list[int]
    required_concepts: list[list[str]]
    minimum_concept_coverage: float


_SOURCE_BY_TITLE = {
    "O sujeito, a Integralidade e a Saúde Mental": (
        "sma-o-sujeito-a-integralidade-e-saude-mental.pdf"
    ),
    "Desenvolvendo os Cuidados de Saúde Mental na APS": (
        "sma-desenvolvendo-os-cuidados-de-saude-mental-na-aps.pdf"
    ),
    "Ampliando o Conceito de Saúde Mental": (
        "sma-u-1-ampliando-o-conceito-de-saude-mental.pdf"
    ),
}
_DATASET = json.loads(
    Path("evaluation/rag_cases.json").read_text(encoding="utf-8")
)
_CASES = cast(list[EvaluationCase], _DATASET["cases"])


def _answer_for(case: EvaluationCase) -> str:
    title = case["expected_title"]
    pages = case["expected_pages"]
    concepts = "; ".join(group[0] for group in case["required_concepts"])
    return f"{concepts}. [{title}, p. {pages[0]}]"


def _retrieved_for(case: EvaluationCase) -> tuple[RetrievedChunk, ...]:
    if not case["answerable"]:
        return ()
    title = case["expected_title"]
    assert title is not None
    page = case["expected_pages"][0]
    chunk = DocumentChunk(
        id=f"{case['id']}-chunk",
        text="; ".join(group[0] for group in case["required_concepts"]),
        source=_SOURCE_BY_TITLE[title],
        title=title,
        page=page,
        content_hash=f"{case['id']}-hash",
    )
    return (RetrievedChunk(chunk=chunk, score=0.95),)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["id"])
async def test_offline_rag_dataset_through_application_service(
    case: EvaluationCase,
) -> None:
    retriever = FakeVectorStore(_retrieved_for(case))
    llm = FakeLLM((_answer_for(case),)) if case["answerable"] else FakeLLM()
    service = GroundedChatService(
        llm=llm,
        retriever=retriever,
        sessions=FakeSessionRepository(),
        models=ModelCatalog(["model-a"]),
        contextualizer=RecentHistoryContextualizer(max_history_messages=4),
        prompt_builder=GroundedPromptBuilder(),
        policy=ChatPolicy(
            max_session_messages=12,
            retrieval_limit=3,
            score_threshold=0.35,
            max_message_length=4000,
        ),
    )
    session_id = f"offline-{case['id']}"

    for question in case["setup_questions"]:
        _ = [
            event
            async for event in service.stream(
                ChatRequest(session_id=session_id, message=question, model="model-a")
            )
        ]
    events = [
        event
        async for event in service.stream(
            ChatRequest(
                session_id=session_id,
                message=case["question"],
                model="model-a",
            )
        )
    ]

    metadata = next(event for event in events if event.type is ChatEventType.METADATA)
    answer = "".join(
        event.content or ""
        for event in events
        if event.type is ChatEventType.TOKEN
    )
    citations = tuple(
        ObservedCitation(
            title=citation.title,
            page=citation.page,
        )
        for citation in metadata.citations
    )
    score = evaluate_answer(
        answer=answer,
        citations=citations,
        answerable=case["answerable"],
        expected_title=case["expected_title"],
        expected_pages=tuple(case["expected_pages"]),
        required_concepts=tuple(
            tuple(alternatives) for alternatives in case["required_concepts"]
        ),
        minimum_concept_coverage=case["minimum_concept_coverage"],
    )

    assert score.passed, score
    if case["setup_questions"]:
        assert retriever.queries[-1].startswith("Contexto recente da conversa:")
    else:
        assert retriever.queries[-1] == case["question"]
