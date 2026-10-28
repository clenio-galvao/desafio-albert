from collections.abc import AsyncGenerator

import pytest

from chatbot.application import ChatEvent, ChatEventType, ChatRequest
from chatbot.application.exceptions import MessageTooLongError
from chatbot.application.use_cases import ModelCatalog
from chatbot.bootstrap import ApplicationContainer, build_container
from chatbot.config import Settings


class EmptyChat:
    def validate(self, request: ChatRequest) -> None:
        pass

    async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
        yield ChatEvent(type=ChatEventType.DONE)


class CloseResource:
    def __init__(self, name: str, closed: list[str]) -> None:
        self.name = name
        self.closed = closed

    async def close(self) -> None:
        self.closed.append(self.name)


class Ready:
    async def execute(self) -> bool:
        return True


class EndSession:
    async def execute(self, session_id: str) -> bool:
        return True


async def test_application_container_closes_resources_in_reverse_order() -> None:
    closed: list[str] = []
    container = ApplicationContainer(
        chat=EmptyChat(),
        models=ModelCatalog(["model"]),
        end_session=EndSession(),
        readiness=Ready(),
        resources=(
            CloseResource("first", closed),
            CloseResource("second", closed),
        ),
    )

    await container.close()

    assert closed == ["second", "first"]


async def test_build_container_composes_real_adapters_without_network_calls() -> None:
    settings = Settings(
        _env_file=None,
        openai_base_url="https://gateway.test/v1",
        openai_api_key="secret",
        qdrant_url="https://qdrant.test",
        qdrant_api_key="secret",
        chat_models="model-a,model-b",
        max_message_length=321,
    )

    container = build_container(settings)

    assert container.models.execute() == ("model-a", "model-b")
    with pytest.raises(MessageTooLongError, match="321"):
        container.chat.validate(
            ChatRequest(session_id="session", message="x" * 322, model="model-a")
        )
    assert len(container.resources) == 3
    await container.close()
