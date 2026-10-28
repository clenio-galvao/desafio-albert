import pytest

from chatbot.adapters.outbound.memory_sessions import InMemorySessionRepository
from chatbot.domain import ChatSession, Message, MessageRole


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize(
    ("ttl_seconds", "max_sessions", "message"),
    [(0, 1, "ttl_seconds"), (10, 0, "max_sessions")],
)
def test_memory_repository_validates_configuration(
    ttl_seconds: int,
    max_sessions: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        InMemorySessionRepository(ttl_seconds=ttl_seconds, max_sessions=max_sessions)


async def test_memory_repository_returns_none_for_missing_session() -> None:
    repository = InMemorySessionRepository(ttl_seconds=10)

    assert await repository.get("missing") is None


async def test_memory_repository_saves_and_returns_session() -> None:
    repository = InMemorySessionRepository(ttl_seconds=10)
    session = ChatSession(id="session", max_messages=2)

    await repository.save(session)

    assert await repository.get("session") == session


async def test_memory_repository_delete_is_idempotent() -> None:
    repository = InMemorySessionRepository(ttl_seconds=10)
    session = ChatSession(id="session", max_messages=2)
    await repository.save(session)

    assert await repository.delete("session") is True
    assert await repository.delete("session") is False


async def test_memory_repository_isolates_stored_state_from_callers() -> None:
    repository = InMemorySessionRepository(ttl_seconds=10)
    session = ChatSession(id="session", max_messages=4)
    await repository.save(session)

    session.add(Message(role=MessageRole.USER, content="não salva"))
    loaded = await repository.get("session")
    assert loaded is not None
    loaded.add(Message(role=MessageRole.USER, content="também não"))

    stored = await repository.get("session")
    assert stored is not None
    assert stored.messages == []


async def test_memory_repository_expires_and_renews_ttl() -> None:
    clock = Clock()
    repository = InMemorySessionRepository(ttl_seconds=10, clock=clock)
    session = ChatSession(id="session", max_messages=2)
    await repository.save(session)

    clock.now = 9
    assert await repository.get("session") == session
    await repository.save(session)

    clock.now = 15
    assert await repository.get("session") == session
    clock.now = 19
    assert await repository.get("session") is None


async def test_memory_repository_purges_expired_sessions_never_read_again() -> None:
    clock = Clock()
    repository = InMemorySessionRepository(ttl_seconds=10, clock=clock)
    for index in range(3):
        await repository.save(ChatSession(id=f"old-{index}", max_messages=2))

    clock.now = 5
    await repository.save(ChatSession(id="recent", max_messages=2))
    clock.now = 10
    await repository.save(ChatSession(id="new", max_messages=2))

    assert await repository.delete("old-0") is False
    assert await repository.delete("old-2") is False
    assert await repository.get("recent") is not None


async def test_memory_repository_evicts_least_recently_saved_beyond_capacity() -> None:
    repository = InMemorySessionRepository(ttl_seconds=10, max_sessions=2)
    await repository.save(ChatSession(id="first", max_messages=2))
    await repository.save(ChatSession(id="second", max_messages=2))
    await repository.save(ChatSession(id="first", max_messages=2))

    await repository.save(ChatSession(id="third", max_messages=2))

    assert await repository.get("second") is None
    assert await repository.get("first") is not None
    assert await repository.get("third") is not None
