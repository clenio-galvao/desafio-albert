import pytest

from chatbot.application.contextualization import RecentHistoryContextualizer
from chatbot.domain import Message, MessageRole


def history() -> list[Message]:
    return [
        Message(MessageRole.USER, "antiga"),
        Message(MessageRole.ASSISTANT, "resposta recente"),
        Message(MessageRole.USER, "pergunta recente"),
    ]


def test_contextualizer_rejects_negative_history_limit() -> None:
    with pytest.raises(ValueError, match="max_history_messages"):
        RecentHistoryContextualizer(-1)


def test_contextualizer_keeps_only_recent_history_window() -> None:
    query = RecentHistoryContextualizer(max_history_messages=2).contextualize(
        "e agora?",
        history(),
    )

    assert "antiga" not in query
    assert "assistant: resposta recente" in query
    assert query.endswith("Pergunta atual: e agora?")


def test_contextualizer_returns_question_when_history_limit_is_zero() -> None:
    assert RecentHistoryContextualizer(0).contextualize("direta", history()) == "direta"


def test_contextualizer_returns_question_when_history_is_empty() -> None:
    contextualizer = RecentHistoryContextualizer(max_history_messages=2)

    assert contextualizer.contextualize("direta", []) == "direta"


def test_contextualizer_skips_self_contained_question() -> None:
    contextualizer = RecentHistoryContextualizer(max_history_messages=2)

    assert (
        contextualizer.contextualize("O que é escuta terapêutica?", history())
        == "O que é escuta terapêutica?"
    )


def test_contextualizer_adds_recent_context_for_vague_follow_up() -> None:
    query = RecentHistoryContextualizer(max_history_messages=2).contextualize(
        "Como funciona?",
        history(),
    )

    assert "Contexto recente" in query
