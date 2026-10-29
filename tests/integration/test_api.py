import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from chatbot.adapters.inbound.api.router import stream_chat
from chatbot.adapters.inbound.api.schemas import ChatBody
from chatbot.application import ChatEvent, ChatEventType, ChatRequest
from chatbot.application.exceptions import (
    ApplicationError,
    ChatValidationError,
    MessageTooLongError,
    UnsupportedModelError,
)
from chatbot.application.observability import ChatOutcome, fingerprint_session
from chatbot.application.stream_gate import ConcurrentStreamGate
from chatbot.application.use_cases import ModelCatalog
from chatbot.bootstrap import ApplicationContainer
from chatbot.domain import Citation
from chatbot.main import create_app

from ..fakes import RecordingObservability


class FakeReadiness:
    def __init__(self, ready: bool = True, error: Exception | None = None) -> None:
        self.value = ready
        self.error = error

    async def execute(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.value


class FakeEndSession:
    def __init__(self) -> None:
        self.session_ids: list[str] = []

    async def execute(self, session_id: str) -> bool:
        self.session_ids.append(session_id)
        return True


class FakeChat:
    def __init__(
        self,
        error: BaseException | None = None,
        tokens: tuple[str, ...] = ("Olá",),
        validation_error: ChatValidationError | None = None,
    ) -> None:
        self.error = error
        self.tokens = tokens
        self.validation_error = validation_error
        self.validated: list[ChatRequest] = []
        self.requests: list[ChatRequest] = []

    def validate(self, request: ChatRequest) -> None:
        self.validated.append(request)
        if self.validation_error is not None:
            raise self.validation_error

    async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
        self.requests.append(request)
        yield ChatEvent(
            type=ChatEventType.METADATA,
            citations=(
                Citation(
                    source="apostila.pdf",
                    title="Apostila",
                    page=3,
                    chunk_id="chunk",
                ),
            ),
        )
        if self.error is not None:
            raise self.error
        for token in self.tokens:
            yield ChatEvent(type=ChatEventType.TOKEN, content=token)
        yield ChatEvent(type=ChatEventType.DONE)


def make_container(
    *,
    chat: FakeChat | None = None,
    readiness: FakeReadiness | None = None,
    end_session: FakeEndSession | None = None,
) -> ApplicationContainer:
    return ApplicationContainer(
        chat=chat or FakeChat(),
        models=ModelCatalog(["model-a", "model-b"]),
        end_session=end_session or FakeEndSession(),
        readiness=readiness or FakeReadiness(),
    )


def make_client(container: ApplicationContainer) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=create_app(container=container)),
        base_url="http://test",
    )


async def test_health_live_returns_ok() -> None:
    async with make_client(make_container()) as client:
        response = await client.get("/health/live")

    assert response.json() == {"status": "ok"}


async def test_health_ready_when_dependencies_ok() -> None:
    async with make_client(make_container()) as client:
        response = await client.get("/health/ready")

    assert response.json() == {"status": "ready"}


async def test_list_models_returns_allowlist() -> None:
    async with make_client(make_container()) as client:
        response = await client.get("/v1/models")

    assert response.json() == {"models": ["model-a", "model-b"]}


async def test_delete_session_returns_204() -> None:
    end_session = FakeEndSession()
    async with make_client(make_container(end_session=end_session)) as client:
        response = await client.delete("/v1/sessions/session")

    assert response.status_code == 204
    assert end_session.session_ids == ["session"]


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


async def test_chat_preserves_multiple_partial_tokens_before_done() -> None:
    async with make_client(make_container(chat=FakeChat(tokens=("par", "cial")))) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={"session_id": "session", "message": "pergunta", "model": "model-a"},
        )

    first = response.text.index('event: token\ndata: {"content":"par"}')
    second = response.text.index('event: token\ndata: {"content":"cial"}')
    done = response.text.index("event: done")
    assert first < second < done


@pytest.mark.parametrize(
    ("payload", "validation_error", "detail"),
    [
        (
            {"session_id": "session", "message": "pergunta", "model": "unknown"},
            UnsupportedModelError("modelo não permitido: unknown"),
            "modelo não permitido",
        ),
        (
            {"session_id": "session", "message": "muito longa", "model": "model-a"},
            MessageTooLongError("message excede o limite de 5 caracteres"),
            "message excede",
        ),
    ],
)
async def test_chat_rejects_invalid_model_or_configured_length(
    payload: dict[str, str],
    validation_error: ChatValidationError,
    detail: str,
) -> None:
    chat = FakeChat(validation_error=validation_error)
    async with make_client(make_container(chat=chat)) as client:
        response = await client.post("/v1/chat/stream", json=payload)

    assert response.status_code == 422
    assert detail in response.json()["detail"]
    assert len(chat.validated) == 1


async def test_chat_schema_rejects_unknown_body_fields() -> None:
    async with make_client(make_container()) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={
                "session_id": "session",
                "message": "pergunta",
                "model": "model-a",
                "api_key": "não deve ser aceito",
            },
        )

    assert response.status_code == 422


async def test_chat_schema_rejects_invalid_session_id() -> None:
    async with make_client(make_container()) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={
                "session_id": "espaço inválido",
                "message": "pergunta",
                "model": "model-a",
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


async def test_chat_rejects_overflow_before_opening_sse() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingChat(FakeChat):
        async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
            started.set()
            await release.wait()
            async for event in super().stream(request):
                yield event

    container = ApplicationContainer(
        chat=BlockingChat(),
        models=ModelCatalog(["model-a"]),
        end_session=FakeEndSession(),
        readiness=FakeReadiness(),
        stream_gate=ConcurrentStreamGate(1),
    )
    async with make_client(container) as client:
        first = asyncio.create_task(
            client.post(
                "/v1/chat/stream",
                json={"session_id": "one", "message": "pergunta", "model": "model-a"},
            )
        )
        await asyncio.wait_for(started.wait(), timeout=2)
        denied = await client.post(
            "/v1/chat/stream",
            json={"session_id": "two", "message": "pergunta", "model": "model-a"},
        )
        release.set()
        completed = await first

    assert denied.status_code == 429
    assert "muitas respostas" in denied.json()["detail"]
    assert completed.status_code == 200


async def test_chat_stream_without_timeout_still_completes() -> None:
    container = ApplicationContainer(
        chat=FakeChat(),
        models=ModelCatalog(["model-a"]),
        end_session=FakeEndSession(),
        readiness=FakeReadiness(),
        stream_timeout_seconds=0,
    )
    async with make_client(container) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={"session_id": "session", "message": "pergunta", "model": "model-a"},
        )

    assert response.status_code == 200
    assert "event: done" in response.text


async def test_chat_emits_timeout_error_when_generation_exceeds_limit() -> None:
    class SlowChat(FakeChat):
        async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
            yield ChatEvent(type=ChatEventType.METADATA)
            await asyncio.sleep(1)
            yield ChatEvent(type=ChatEventType.TOKEN, content="tarde")
            yield ChatEvent(type=ChatEventType.DONE)

    container = ApplicationContainer(
        chat=SlowChat(),
        models=ModelCatalog(["model-a"]),
        end_session=FakeEndSession(),
        readiness=FakeReadiness(),
        stream_timeout_seconds=0.05,
    )
    async with make_client(container) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={"session_id": "session", "message": "pergunta", "model": "model-a"},
        )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "tempo esgotado" in response.text


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

    request = Request(
        {"type": "http", "method": "POST", "path": "/", "headers": []},
        receive,
    )
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


def _cors_app() -> FastAPI:
    return create_app(
        container=make_container(),
        cors_origins=("https://frontend.test",),
    )


async def test_cors_allows_configured_origin() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_cors_app()),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/v1/models",
            headers={
                "Origin": "https://frontend.test",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.headers["access-control-allow-origin"] == "https://frontend.test"


async def test_cors_rejects_unknown_origin() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_cors_app()),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/v1/models",
            headers={
                "Origin": "https://attacker.test",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert "access-control-allow-origin" not in response.headers


async def test_cors_preflight_allows_stream_headers() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_cors_app()),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/v1/chat/stream",
            headers={
                "Origin": "https://frontend.test",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,X-Request-ID",
            },
        )

    allowed = response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-allow-origin"] == "https://frontend.test"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in allowed
    assert "x-request-id" in allowed


async def test_cors_stream_exposes_request_id() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_cors_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/v1/chat/stream",
            headers={"Origin": "https://frontend.test"},
            json={"session_id": "session-1", "message": "Olá", "model": "model-a"},
        )

    exposed = response.headers["access-control-expose-headers"].lower()
    assert response.headers["access-control-allow-origin"] == "https://frontend.test"
    assert "x-request-id" in exposed


async def test_cors_omits_credentials() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_cors_app()),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/v1/models",
            headers={
                "Origin": "https://frontend.test",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert "access-control-allow-credentials" not in response.headers


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
    assert "Fontes consultadas:" in response.text
    assert "formatPages(pages)" in response.text
    assert "OPENAI_API_KEY" not in response.text
    assert "QDRANT_API_KEY" not in response.text


async def test_http_echoes_a_safe_request_id() -> None:
    async with make_client(make_container()) as client:
        response = await client.get("/health/live", headers={"X-Request-ID": "req-123"})

    assert response.headers["x-request-id"] == "req-123"


async def test_http_generates_request_id_when_missing() -> None:
    async with make_client(make_container()) as client:
        response = await client.get("/health/live")

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    assert request_id.isalnum()


async def test_http_replaces_unsafe_request_id() -> None:
    async with make_client(make_container()) as client:
        response = await client.get("/health/live", headers={"X-Request-ID": "bad id"})

    assert response.headers["x-request-id"] != "bad id"
    assert " " not in response.headers["x-request-id"]


async def test_completed_stream_records_operational_outcome() -> None:
    recording = RecordingObservability()
    chat = FakeChat(tokens=("Olá", " mundo"))
    container = make_container(chat=chat)
    container = ApplicationContainer(
        chat=chat,
        models=container.models,
        end_session=container.end_session,
        readiness=container.readiness,
        observability=recording,
    )
    async with make_client(container) as client:
        response = await client.post(
            "/v1/chat/stream",
            headers={"X-Request-ID": "req-stream"},
            json={"session_id": "session", "message": "pergunta clínica", "model": "model-a"},
        )

    observation = recording.observations[0]
    assert response.headers["x-request-id"] == "req-stream"
    assert observation.outcome is ChatOutcome.COMPLETED
    assert observation.request_id == "req-stream"
    assert observation.citation_count == 1
    assert observation.first_token_seconds is not None
    assert observation.session_fingerprint == fingerprint_session("session")
    assert "pergunta clínica" not in str(recording.observations)


async def test_refused_stream_records_refusal() -> None:
    recording = RecordingObservability()

    class RefusingChat(FakeChat):
        async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
            yield ChatEvent(type=ChatEventType.METADATA)
            yield ChatEvent(type=ChatEventType.TOKEN, content="recusa")
            yield ChatEvent(type=ChatEventType.DONE)

    container = ApplicationContainer(
        chat=RefusingChat(),
        models=ModelCatalog(["model-a"]),
        end_session=FakeEndSession(),
        readiness=FakeReadiness(),
        observability=recording,
    )
    async with make_client(container) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={"session_id": "session", "message": "pergunta", "model": "model-a"},
        )

    assert response.status_code == 200
    assert recording.observations[0].outcome is ChatOutcome.REFUSED
    assert recording.observations[0].citation_count == 0


async def test_rejected_stream_records_admission_failure() -> None:
    recording = RecordingObservability()
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingChat(FakeChat):
        async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
            started.set()
            await release.wait()
            async for event in super().stream(request):
                yield event

    container = ApplicationContainer(
        chat=BlockingChat(),
        models=ModelCatalog(["model-a"]),
        end_session=FakeEndSession(),
        readiness=FakeReadiness(),
        stream_gate=ConcurrentStreamGate(1),
        observability=recording,
    )
    async with make_client(container) as client:
        first = asyncio.create_task(
            client.post(
                "/v1/chat/stream",
                json={"session_id": "one", "message": "pergunta", "model": "model-a"},
            )
        )
        await asyncio.wait_for(started.wait(), timeout=2)
        denied = await client.post(
            "/v1/chat/stream",
            json={"session_id": "two", "message": "pergunta", "model": "model-a"},
        )
        release.set()
        await first

    assert denied.status_code == 429
    assert len(recording.rejections) == 1
    assert recording.rejections[0][1] == fingerprint_session("two")


async def test_timeout_records_timeout_outcome() -> None:
    recording = RecordingObservability()

    class SlowChat(FakeChat):
        async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
            yield ChatEvent(type=ChatEventType.METADATA)
            await asyncio.sleep(1)
            yield ChatEvent(type=ChatEventType.TOKEN, content="tarde")
            yield ChatEvent(type=ChatEventType.DONE)

    container = ApplicationContainer(
        chat=SlowChat(),
        models=ModelCatalog(["model-a"]),
        end_session=FakeEndSession(),
        readiness=FakeReadiness(),
        stream_timeout_seconds=0.05,
        observability=recording,
    )
    async with make_client(container) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={"session_id": "session", "message": "pergunta", "model": "model-a"},
        )

    assert response.status_code == 200
    assert recording.observations[0].outcome is ChatOutcome.TIMEOUT
    assert recording.observations[0].first_token_seconds is None


async def test_disconnect_records_disconnected_outcome() -> None:
    recording = RecordingObservability()
    container = ApplicationContainer(
        chat=FakeChat(),
        models=ModelCatalog(["model-a"]),
        end_session=FakeEndSession(),
        readiness=FakeReadiness(),
        observability=recording,
    )
    with patch(
        "starlette.requests.Request.is_disconnected",
        new=AsyncMock(return_value=True),
    ):
        async with make_client(container) as client:
            response = await client.post(
                "/v1/chat/stream",
                json={"session_id": "session", "message": "pergunta", "model": "model-a"},
            )

    assert response.status_code == 200
    assert recording.observations[0].outcome is ChatOutcome.DISCONNECTED


async def test_stream_error_records_error_outcome() -> None:
    recording = RecordingObservability()
    container = ApplicationContainer(
        chat=FakeChat(RuntimeError("falha")),
        models=ModelCatalog(["model-a"]),
        end_session=FakeEndSession(),
        readiness=FakeReadiness(),
        observability=recording,
    )
    async with make_client(container) as client:
        response = await client.post(
            "/v1/chat/stream",
            json={"session_id": "session", "message": "pergunta", "model": "model-a"},
        )

    assert "event: error" in response.text
    assert recording.observations[0].outcome is ChatOutcome.ERROR
    assert "falha" not in response.text
