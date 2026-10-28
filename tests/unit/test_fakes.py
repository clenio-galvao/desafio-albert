from chatbot.domain import ChatSession, Message, MessageRole

from ..fakes import FakeSessionRepository


async def test_fake_session_repository_isolates_callers_from_stored_state() -> None:
    repository = FakeSessionRepository()
    session = ChatSession(id="session", max_messages=4)
    await repository.save(session)

    session.add(Message(role=MessageRole.USER, content="não salva"))
    loaded = await repository.get("session")
    assert loaded is not None
    loaded.add(Message(role=MessageRole.USER, content="também não"))

    stored = await repository.get("session")
    assert stored is not None
    assert stored.messages == []
