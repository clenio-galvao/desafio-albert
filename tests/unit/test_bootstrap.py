from collections.abc import AsyncGenerator

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from chatbot.adapters.outbound.telemetry.logging_adapter import LoggingObservability
from chatbot.adapters.outbound.telemetry.otlp import OpenTelemetryObservability
from chatbot.application import ChatEvent, ChatEventType, ChatRequest
from chatbot.application.exceptions import MessageTooLongError
from chatbot.application.retrieval import SemanticRetriever
from chatbot.application.stream_gate import ConcurrentStreamGate
from chatbot.application.use_cases import GroundedChatService, ModelCatalog
from chatbot.bootstrap import (
    ApplicationContainer,
    build_container,
    build_ingestion,
    build_load_container,
)
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

    assert isinstance(container.observability, LoggingObservability)
    assert isinstance(container.chat, GroundedChatService)
    assert container.chat._observability is container.observability
    retriever = container.chat._retriever
    assert isinstance(retriever, SemanticRetriever)
    assert retriever._observability is container.observability
    assert container.models.execute() == ("model-a", "model-b")
    with pytest.raises(MessageTooLongError, match="321"):
        container.chat.validate(
            ChatRequest(session_id="session", message="x" * 322, model="model-a")
        )
    assert len(container.resources) == 3
    await container.close()


async def test_build_container_closes_otlp_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer_provider = TracerProvider(shutdown_on_exit=False)
    tracer_provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    observability = OpenTelemetryObservability(
        tracer_provider=tracer_provider,
        meter_provider=MeterProvider(
            metric_readers=[InMemoryMetricReader()],
            shutdown_on_exit=False,
        ),
        stream_gate=ConcurrentStreamGate(1),
    )
    monkeypatch.setattr(
        "chatbot.bootstrap.build_observability",
        lambda _settings, _stream_gate: observability,
    )
    container = build_container(
        Settings(
            _env_file=None,
            openai_base_url="https://gateway.test/v1",
            openai_api_key="secret",
            qdrant_url="https://qdrant.test",
            qdrant_api_key="secret",
            chat_models="model-a",
        )
    )

    assert observability in container.resources
    await container.close()


async def test_build_ingestion_wires_pdf_pipeline_without_network_calls() -> None:
    settings = Settings(
        _env_file=None,
        openai_base_url="https://gateway.test/v1",
        openai_api_key="secret",
        qdrant_url="https://qdrant.test",
        qdrant_api_key="secret",
        chat_models="model-a,model-b",
    )

    ingestion = build_ingestion(settings)

    assert len(ingestion.resources) == 2
    await ingestion.close()


async def test_build_load_container_serves_chat_without_external_clients() -> None:
    container = build_load_container(token_delay_seconds=0.0, max_concurrent_streams=2)

    assert await container.stream_gate.try_acquire() is True
    assert await container.stream_gate.try_acquire() is True
    assert await container.stream_gate.try_acquire() is False
    await container.stream_gate.release()
    await container.stream_gate.release()

    events = [
        event
        async for event in container.chat.stream(
            ChatRequest(
                session_id="load",
                message="pergunta",
                model="azure/gpt-5-mini",
            )
        )
    ]
    assert events[0].type is ChatEventType.METADATA
    assert events[-1].type is ChatEventType.DONE
    assert await container.readiness.execute() is True
