import json
import logging
import sys

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from starlette.types import Message, Receive, Scope, Send

from chatbot.adapters.inbound.api.request_id import RequestIdMiddleware
from chatbot.adapters.outbound.telemetry.json_logging import JsonLogFormatter, configure_logging
from chatbot.adapters.outbound.telemetry.logging_adapter import LoggingObservability
from chatbot.adapters.outbound.telemetry.otlp import (
    OpenTelemetryObservability,
    build_observability,
    build_otlp_observability,
    build_otlp_signal_endpoint,
    parse_otlp_headers,
)
from chatbot.application.observability import (
    ChatObservation,
    ChatOutcome,
    NullObservability,
    fingerprint_session,
)
from chatbot.application.request_context import bind_request_id, reset_request_id
from chatbot.application.stream_gate import ConcurrentStreamGate

from ..fakes import RecordingObservability
from .test_config import make_settings


def _observation(**changes: object) -> ChatObservation:
    values: dict[str, object] = {
        "request_id": "req-1",
        "session_fingerprint": "abc123",
        "model": "model-a",
        "outcome": ChatOutcome.COMPLETED,
        "citation_count": 1,
        "best_score": 0.8,
        "first_token_seconds": 0.2,
        "duration_seconds": 0.5,
    }
    values.update(changes)
    return ChatObservation(**values)  # type: ignore[arg-type]


def _memory_observability(
    gate: ConcurrentStreamGate | None = None,
) -> tuple[OpenTelemetryObservability, InMemorySpanExporter, InMemoryMetricReader]:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider(shutdown_on_exit=False)
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    observability = OpenTelemetryObservability(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        stream_gate=gate,
    )
    return observability, exporter, reader


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    data = reader.get_metrics_data()
    if data is None:
        return set()
    return {
        metric.name
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }


async def test_request_id_middleware_ignores_non_http_scope() -> None:
    seen: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        del receive, send
        seen.append(str(scope["type"]))

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        del message

    await RequestIdMiddleware(app)({"type": "lifespan"}, receive, send)

    assert seen == ["lifespan"]


def test_fingerprint_session_hides_the_original_identifier() -> None:
    fingerprint = fingerprint_session("session-clinica")

    assert fingerprint != "session-clinica"
    assert fingerprint == fingerprint_session("session-clinica")
    assert len(fingerprint) == 16


def test_null_observability_accepts_spans_and_outcomes() -> None:
    observability = NullObservability()

    with observability.start_span("chat.stream", {"chat.model": "model-a"}) as span:
        span.set_attribute("chat.refused", False)
    observability.record_chat(_observation())
    observability.record_admission_rejected(request_id="req-1", session_fingerprint="abc")


def test_logging_observability_omits_conversation_text(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="chatbot.observability")
    observability = LoggingObservability()

    with observability.start_span("chat.stream") as span:
        span.set_attribute("chat.model", "model-a")
    observability.record_chat(_observation())

    assert "chat_stream" in caplog.text
    assert "pergunta clínica" not in caplog.text
    assert caplog.records[0].session_fingerprint == "abc123"  # type: ignore[attr-defined]


def test_logging_observability_records_admission_rejection(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="chatbot.observability")
    LoggingObservability().record_admission_rejected(
        request_id="req-9",
        session_fingerprint="fingerprint",
    )

    assert "chat_admission_rejected" in caplog.text
    assert caplog.records[0].request_id == "req-9"  # type: ignore[attr-defined]


def test_json_log_includes_bound_request_id() -> None:
    record = logging.LogRecord(
        name="chatbot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="chat_stream",
        args=(),
        exc_info=None,
    )
    token = bind_request_id("req-123")
    try:
        payload = json.loads(JsonLogFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["request_id"] == "req-123"
    assert payload["message"] == "chat_stream"


def test_json_log_keeps_only_operational_fields() -> None:
    record = logging.LogRecord(
        name="chatbot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="chat_stream",
        args=(),
        exc_info=None,
    )
    record.session_fingerprint = "abc"
    record.session_id = "session-real"
    record.message_text = "texto clínico"

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["session_fingerprint"] == "abc"
    assert "session_id" not in payload
    assert "texto clínico" not in json.dumps(payload)
    assert "request_id" not in payload


def test_json_log_includes_exception_text() -> None:
    try:
        raise RuntimeError("falha interna")
    except RuntimeError:
        record = logging.LogRecord(
            name="chatbot.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="chat_unexpected_error",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(JsonLogFormatter().format(record))

    assert "RuntimeError" in payload["exception"]
    assert "falha interna" in payload["exception"]


def test_json_log_includes_current_trace_id() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    record = logging.LogRecord(
        name="chatbot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="chat_stream",
        args=(),
        exc_info=None,
    )
    try:
        with provider.get_tracer("chatbot").start_as_current_span("chat.stream"):
            payload = json.loads(JsonLogFormatter().format(record))
    finally:
        provider.shutdown()

    assert len(payload["trace_id"]) == 32
    assert len(payload["span_id"]) == 16


def test_configure_logging_sets_level_once() -> None:
    root = logging.getLogger()
    previous = root.level
    try:
        configure_logging("WARNING")
        configure_logging("ERROR")
        assert root.level == logging.ERROR
        assert [handler.get_name() for handler in root.handlers].count("chatbot-json") == 1
    finally:
        root.setLevel(previous)


def test_configure_logging_falls_back_to_info() -> None:
    root = logging.getLogger()
    previous = root.level
    try:
        configure_logging("not-a-level")
        assert root.level == logging.INFO
    finally:
        root.setLevel(previous)


def test_parse_otlp_headers_decodes_authorization() -> None:
    headers = parse_otlp_headers("Authorization=Basic%20token, x-scope=metrics")

    assert headers == {"Authorization": "Basic token", "x-scope": "metrics"}


def test_parse_otlp_headers_ignores_broken_entries() -> None:
    assert parse_otlp_headers(" , sem-igual, =vazio") == {}


def test_signal_endpoint_appends_traces_path() -> None:
    assert (
        build_otlp_signal_endpoint("https://otlp.example/otlp/", "traces")
        == "https://otlp.example/otlp/v1/traces"
    )


def test_signal_endpoint_replaces_existing_signal_suffix() -> None:
    assert (
        build_otlp_signal_endpoint("https://otlp.example/v1/metrics", "traces")
        == "https://otlp.example/v1/traces"
    )


def test_build_observability_stays_local_without_endpoint() -> None:
    observability = build_observability(make_settings(), ConcurrentStreamGate(1))

    assert isinstance(observability, LoggingObservability)


def test_build_observability_disables_export_when_setup_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(settings: object, stream_gate: object) -> OpenTelemetryObservability:
        del settings, stream_gate
        raise RuntimeError("otlp indisponível")

    caplog.set_level(logging.ERROR)
    observability = build_observability(
        make_settings(otel_exporter_otlp_endpoint="https://otlp.example"),
        ConcurrentStreamGate(1),
        provider_factory=fail,
    )

    assert isinstance(observability, LoggingObservability)
    assert "observability_export_disabled" in caplog.text


async def test_otlp_span_keeps_operational_attributes_only() -> None:
    observability, exporter, _reader = _memory_observability()
    try:
        with observability.start_span(
            "chat.stream",
            {"chat.model": "model-a", "session.fingerprint": "abc"},
        ) as span:
            span.set_attribute("chat.refused", False)
    finally:
        await observability.close()

    finished = exporter.get_finished_spans()
    assert finished[0].name == "chat.stream"
    assert finished[0].attributes is not None
    assert finished[0].attributes["chat.model"] == "model-a"
    assert "message" not in finished[0].attributes


async def test_otlp_span_marks_errors_and_records_llm_latency() -> None:
    observability, exporter, reader = _memory_observability()
    try:
        with (
            pytest.raises(RuntimeError, match="falha"),
            observability.start_span("llm", {"chat.model": "model-a"}),
        ):
            raise RuntimeError("falha")
    finally:
        await observability.close()

    finished = exporter.get_finished_spans()
    assert finished[0].status.status_code is StatusCode.ERROR
    assert "chat.llm_seconds" in _metric_names(reader)


async def test_otlp_records_qdrant_latency_and_active_streams() -> None:
    gate = ConcurrentStreamGate(4)
    await gate.try_acquire()
    observability, _exporter, reader = _memory_observability(gate)
    try:
        with observability.start_span("qdrant"):
            pass
        observability.record_chat(
            _observation(
                best_score=None,
                first_token_seconds=None,
                duration_seconds=None,
            )
        )
        observability.record_admission_rejected(request_id="req-1", session_fingerprint="abc")
        names = _metric_names(reader)
    finally:
        await observability.close()

    assert {
        "chat.qdrant_seconds",
        "chat.streams",
        "chat.admission_rejected",
        "chat.streams_active",
    } <= names
    assert "chat.first_token_seconds" not in names


async def test_otlp_records_client_latencies() -> None:
    observability, _exporter, reader = _memory_observability()
    try:
        observability.record_chat(_observation())
        names = _metric_names(reader)
    finally:
        await observability.close()

    assert "chat.first_token_seconds" in names
    assert "chat.stream_duration_seconds" in names


async def test_build_otlp_observability_targets_signal_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Exporter:
        def __init__(
            self,
            endpoint: str,
            headers: dict[str, str] | None = None,
            **_kwargs: object,
        ) -> None:
            self.endpoint = endpoint
            self.headers = headers or {}

    class _Processor:
        def __init__(self, exporter: _Exporter) -> None:
            captured["traces"] = exporter.endpoint
            captured["headers"] = exporter.headers

        def on_start(self, span: object, parent_context: object = None) -> None:
            return None

        def on_end(self, span: object) -> None:
            return None

        def shutdown(self) -> None:
            return None

        def force_flush(self, timeout_millis: int = 0) -> bool:
            return True

    class _Reader(InMemoryMetricReader):
        def __init__(self, exporter: _Exporter, *_args: object, **_kwargs: object) -> None:
            captured["metrics"] = exporter.endpoint
            super().__init__()

    monkeypatch.setattr(
        "chatbot.adapters.outbound.telemetry.otlp.OTLPSpanExporter",
        _Exporter,
    )
    monkeypatch.setattr(
        "chatbot.adapters.outbound.telemetry.otlp.OTLPMetricExporter",
        _Exporter,
    )
    monkeypatch.setattr(
        "chatbot.adapters.outbound.telemetry.otlp.BatchSpanProcessor",
        _Processor,
    )
    monkeypatch.setattr(
        "chatbot.adapters.outbound.telemetry.otlp.PeriodicExportingMetricReader",
        _Reader,
    )
    observability = build_otlp_observability(
        make_settings(
            otel_exporter_otlp_endpoint="https://otlp.example/otlp",
            otel_exporter_otlp_headers="Authorization=Basic%20token",
        ),
        ConcurrentStreamGate(2),
    )
    try:
        assert captured["traces"] == "https://otlp.example/otlp/v1/traces"
        assert captured["metrics"] == "https://otlp.example/otlp/v1/metrics"
        assert captured["headers"] == {"Authorization": "Basic token"}
    finally:
        await observability.close()


def test_recording_observability_is_available_to_other_suites() -> None:
    recording = RecordingObservability()
    recording.record_chat(_observation())

    assert recording.observations[0].outcome is ChatOutcome.COMPLETED
