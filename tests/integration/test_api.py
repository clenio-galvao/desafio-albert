import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from chatbot.adapters.inbound.api.router import stream_chat
from chatbot.adapters.inbound.api.schemas import ChatBody
from chatbot.application import ChatEvent, ChatEventType, ChatRequest
from chatbot.application.exceptions import ApplicationError
from chatbot.application.use_cases import ModelCatalog
from chatbot.bootstrap import ApplicationContainer
from chatbot.domain import ChatSession, Citation
from chatbot.main import create_app

from ..fakes import FakeSessionRepository


class FakeReadiness:
    def __init__(self, ready: bool = True, error: Exception | None = None) -> None:
        self.value = ready
        self.error = error

    async def ready(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.value


class FakeChat:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.requests: list[ChatRequest] = []

    async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
        self.requests.append(request)
        yield ChatEvent(
            type=ChatEventType.METADATA,
            citations=(Citation(source="apostila.pdf", page=3, chunk_id="chunk"),),
        )
        if self.error is not None:
            raise self.error
        yield ChatEvent(type=ChatEventType.TOKEN, content="Olá")
        yield ChatEvent(type=ChatEventType.DONE)


def make_container(
    *,
    chat: FakeChat | None = None,
    readiness: FakeReadiness | None = None,
    max_message_length: int = 100,
) -> ApplicationContainer:
    return ApplicationContainer(
        chat=chat or FakeChat(),
        models=ModelCatalog(["model-a", "model-b"]),
        sessions=FakeSessionRepository(),
        readiness=readiness or FakeReadiness(),
        max_message_length=max_message_length,
    )


def make_client(container: ApplicationContainer) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=create_app(container=container)),
        base_url="http://test",
    )


async def test_health_models_and_session_contracts() -> None:
    container = make_container()
    await container.sessions.save(
        ChatSession(id="session", max_messages=2)
    )
    async with make_client(container) as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
        models = await client.get("/v1/models")
        deleted = await client.delete("/v1/sessions/session")

    assert live.json() == {"status": "ok"}
    assert ready.json() == {"status": "ready"}
    assert models.json() == {"models": ["model-a", "model-b"]}
    assert deleted.status_code == 204
    assert await container.sessions.get("session") is None


@pytest.mark.parametrize(
    "readiness",
    [FakeReadiness(False), FakeReadiness(error=RuntimeError("offline"))],
)
async def test_readiness_returns_503_when_knowledge_base_is_unavailable(
    readiness: FakeReadiness,
) -> None:
    async with make_client(make_container(readiness=readiness)) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "base de conhecimento indisponível"


async def test_chat_stream_exposes_ordered_sse_events() -> None:
    chat = FakeChat()
    async with make_client(make_container(chat=chat)) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={"session_id": "session-1", "message": "Pergunta", "model": "model-a"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.text.count("\n\n") == 3
    assert "event: metadata" in response.text
    assert '"source":"apostila.pdf"' in response.text
    assert '"title":"Apostila"' in response.text
    assert "event: token\ndata: {\"content\":\"Olá\"}" in response.text
    assert response.text.endswith("event: done\ndata: {}\n\n")
    assert chat.requests[0].session_id == "session-1"


@pytest.mark.parametrize(
    ("payload", "max_length", "detail"),
    [
        (
            {"session_id": "session", "message": "pergunta", "model": "unknown"},
            100,
            "modelo não permitido",
        ),
        (
            {"session_id": "session", "message": "muito longa", "model": "model-a"},
            5,
            "message excede",
        ),
    ],
)
async def test_chat_rejects_invalid_model_or_configured_length(
    payload: dict[str, str],
    max_length: int,
    detail: str,
) -> None:
    async with make_client(make_container(max_message_length=max_length)) as client:
        response = await client.post("/v1/chat/stream", json=payload)

    assert response.status_code == 422
    assert detail in response.json()["detail"]


async def test_chat_schema_rejects_extra_fields_and_invalid_session() -> None:
    async with make_client(make_container()) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={
                "session_id": "espaço inválido",
                "message": "pergunta",
                "model": "model-a",
                "api_key": "não deve ser aceito",
            },
        )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ApplicationError("falha"), "Não foi possível concluir a resposta."),
        (RuntimeError("falha"), "Erro interno ao gerar a resposta."),
    ],
)
async def test_chat_converts_stream_failures_to_safe_error_events(
    error: Exception,
    expected: str,
) -> None:
    async with make_client(make_container(chat=FakeChat(error))) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={"session_id": "session", "message": "pergunta", "model": "model-a"},
        )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert expected in response.text
    assert "falha" not in response.text


async def test_chat_stops_stream_when_client_disconnects() -> None:
    with patch(
        "starlette.requests.Request.is_disconnected",
        new=AsyncMock(return_value=True),
    ):
        async with make_client(make_container()) as client:
            response = await client.post(
                "/v1/chat/stream",
                json={"session_id": "session", "message": "pergunta", "model": "model-a"},
            )

    assert response.status_code == 200
    assert response.text == ""


async def test_chat_propagates_task_cancellation() -> None:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request({"type": "http", "method": "POST", "path": "/"}, receive)
    response = await stream_chat(
        ChatBody(session_id="session", message="pergunta", model="model-a"),
        request,
        make_container(chat=FakeChat(asyncio.CancelledError())),
    )

    iterator = response.body_iterator.__aiter__()
    first_event = await anext(iterator)
    with pytest.raises(asyncio.CancelledError):
        await anext(iterator)

    assert "event: metadata" in first_event

async def test_routes_that_need_container_return_503_without_lifespan() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/v1/models")

    assert response.status_code == 503


async def test_cors_allows_only_explicit_origin() -> None:
    application = create_app(
        container=make_container(),
        cors_origins=("https://frontend.test",),
    )
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        allowed = await client.options(
            "/v1/models",
            headers={
                "Origin": "https://frontend.test",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = await client.options(
            "/v1/models",
            headers={
                "Origin": "https://attacker.test",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.headers["access-control-allow-origin"] == "https://frontend.test"
    assert "access-control-allow-origin" not in denied.headers


async def test_demo_contains_streaming_client_without_backend_secrets() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/demo")

    assert response.status_code == 200
    assert "Chatbot de saúde mental" in response.text
    assert 'fetch("/v1/models")' in response.text
    assert 'fetch("/v1/chat/stream"' in response.text
    assert "response.body.getReader()" in response.text
    assert "OPENAI_API_KEY" not in response.text
    assert "QDRANT_API_KEY" not in response.text
