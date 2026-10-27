from datetime import UTC

import pytest

from chatbot.domain import (
    ChatSession,
    Citation,
    DocumentChunk,
    EmptyContentError,
    InvalidPageError,
    Message,
    MessageRole,
    RetrievedChunk,
    SessionLimitError,
)


def make_message(content: str = "conteúdo") -> Message:
    return Message(role=MessageRole.USER, content=content)


def make_chunk(**changes: object) -> DocumentChunk:
    values: dict[str, object] = {
        "id": "chunk-1",
        "text": "Trecho da apostila",
        "source": "apostila.pdf",
        "page": 3,
        "content_hash": "hash-1",
    }
    values.update(changes)
    return DocumentChunk(**values)  # type: ignore[arg-type]


def test_message_normalizes_content_and_uses_utc() -> None:
    message = make_message("  olá  ")

    assert message.content == "olá"
    assert message.created_at.tzinfo is UTC


def test_message_rejects_empty_content() -> None:
    with pytest.raises(EmptyContentError, match="content"):
        make_message("   ")


def test_citation_normalizes_fields_and_validates_page() -> None:
    citation = Citation(source=" apostila.pdf ", page=2, chunk_id=" trecho-1 ")

    assert citation.source == "apostila.pdf"
    assert citation.chunk_id == "trecho-1"

    with pytest.raises(InvalidPageError):
        Citation(source="apostila.pdf", page=0, chunk_id="trecho-1")


@pytest.mark.parametrize("field", ["source", "chunk_id"])
def test_citation_rejects_empty_required_fields(field: str) -> None:
    values = {"source": "apostila.pdf", "page": 1, "chunk_id": "trecho-1"}
    values[field] = " "

    with pytest.raises(EmptyContentError, match=field):
        Citation(**values)  # type: ignore[arg-type]


def test_document_chunk_normalizes_fields_and_builds_citation() -> None:
    chunk = make_chunk(id=" chunk-1 ", text=" texto ", source=" fonte ", content_hash=" hash ")

    assert chunk.id == "chunk-1"
    assert chunk.text == "texto"
    assert chunk.citation() == Citation(source="fonte", page=3, chunk_id="chunk-1")


@pytest.mark.parametrize("field", ["id", "text", "source", "content_hash"])
def test_document_chunk_rejects_empty_required_fields(field: str) -> None:
    with pytest.raises(EmptyContentError, match=field):
        make_chunk(**{field: " "})


def test_document_chunk_rejects_invalid_page() -> None:
    with pytest.raises(InvalidPageError):
        make_chunk(page=0)


@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_retrieved_chunk_rejects_score_outside_unit_interval(score: float) -> None:
    with pytest.raises(ValueError, match="score"):
        RetrievedChunk(chunk=make_chunk(), score=score)


def test_retrieved_chunk_accepts_boundary_scores() -> None:
    assert RetrievedChunk(chunk=make_chunk(), score=0).score == 0
    assert RetrievedChunk(chunk=make_chunk(), score=1).score == 1


def test_chat_session_keeps_only_recent_messages() -> None:
    session = ChatSession(id=" session-1 ", max_messages=2)
    previous_update = session.updated_at

    session.add(make_message("primeira"))
    session.add(make_message("segunda"))
    session.add(make_message("terceira"))

    assert session.id == "session-1"
    assert [message.content for message in session.recent(2)] == ["segunda", "terceira"]
    assert session.updated_at >= previous_update


def test_chat_session_validates_configuration_and_initial_history() -> None:
    with pytest.raises(EmptyContentError, match="id"):
        ChatSession(id=" ", max_messages=2)
    with pytest.raises(ValueError, match="max_messages"):
        ChatSession(id="session", max_messages=1)
    with pytest.raises(SessionLimitError):
        ChatSession(
            id="session",
            max_messages=2,
            messages=[make_message("1"), make_message("2"), make_message("3")],
        )


def test_chat_session_rejects_invalid_recent_limit() -> None:
    session = ChatSession(id="session", max_messages=2)

    with pytest.raises(ValueError, match="limit"):
        session.recent(0)
