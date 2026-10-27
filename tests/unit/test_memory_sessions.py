import pytest

from chatbot.adapters.outbound.memory_sessions import InMemorySessionRepository
from chatbot.domain import ChatSession


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_memory_repository_validates_ttl() -> None:
    with pytest.raises(ValueError, match="ttl_seconds"):
        InMemorySessionRepository(ttl_seconds=0)


async def test_memory_repository_saves_gets_and_deletes_session() -> None:
    repository = InMemorySessionRepository(ttl_seconds=10)
    session = ChatSession(id="session", max_messages=2)

    assert await repository.get("missing") is None
    await repository.save(session)
    assert await repository.get("session") is session
    assert await repository.delete("session") is True
    assert await repository.delete("session") is False


async def test_memory_repository_expires_and_renews_ttl() -> None:
    clock = Clock()
    repository = InMemorySessionRepository(ttl_seconds=10, clock=clock)
    session = ChatSession(id="session", max_messages=2)
    await repository.save(session)

    clock.now = 9
    assert await repository.get("session") is session
    await repository.save(session)

    clock.now = 15
    assert await repository.get("session") is session
    clock.now = 19
    assert await repository.get("session") is None
