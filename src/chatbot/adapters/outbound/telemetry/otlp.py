"""Exportação OTLP de traces e métricas, desligável sem derrubar a API."""

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from time import perf_counter
from urllib.parse import unquote

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, Status, StatusCode

from chatbot.adapters.outbound.telemetry.json_logging import log_admission_rejected, log_chat
from chatbot.adapters.outbound.telemetry.logging_adapter import LoggingObservability
from chatbot.application.observability import ChatObservation
from chatbot.application.ports import ObservabilityPort, StreamGate
from chatbot.application.stream_gate import ConcurrentStreamGate
from chatbot.config import Settings

logger = logging.getLogger(__name__)

_SIGNAL_SUFFIXES = ("/v1/traces", "/v1/metrics", "/v1/logs")


class _OtelSpanAttributes:
    """Adapta o span do SDK à porta, aceitando só atributos operacionais."""

    def __init__(self, span: Span) -> None:
        self._span = span

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        """Encaminha o atributo ao span corrente."""
        self._span.set_attribute(key, value)


class OpenTelemetryObservability:
    """Envia traces e métricas ao Grafana e mantém o log JSON local."""

    def __init__(
        self,
        *,
        tracer_provider: TracerProvider,
        meter_provider: MeterProvider,
        stream_gate: StreamGate | None = None,
    ) -> None:
        self._tracer_provider = tracer_provider
        self._meter_provider = meter_provider
        tracer = tracer_provider.get_tracer("chatbot")
        meter = meter_provider.get_meter("chatbot")
        self._tracer = tracer
        self._streams = meter.create_counter(
            "chat.streams",
            description="Streams SSE encerrados, por desfecho.",
        )
        self._rejected = meter.create_counter(
            "chat.admission_rejected",
            description="Streams recusados porque o gate estava cheio.",
        )
        self._first_token = meter.create_histogram(
            "chat.first_token_seconds",
            unit="s",
            description="Segundos até o primeiro token.",
        )
        self._duration = meter.create_histogram(
            "chat.stream_duration_seconds",
            unit="s",
            description="Duração total do stream.",
        )
        self._qdrant_latency = meter.create_histogram(
            "chat.qdrant_seconds",
            unit="s",
            description="Latência da consulta ao Qdrant.",
        )
        self._llm_latency = meter.create_histogram(
            "chat.llm_seconds",
            unit="s",
            description="Latência da geração no gateway.",
        )
        if isinstance(stream_gate, ConcurrentStreamGate):
            gate = stream_gate

            def observe_active_streams(options: object) -> Iterable[Observation]:
                del options
                return (Observation(gate.active, {"stream.limit": gate.limit}),)

            meter.create_observable_gauge(
                "chat.streams_active",
                callbacks=[observe_active_streams],
                unit="1",
                description="Streams SSE admitidos neste processo.",
            )

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> Iterator[_OtelSpanAttributes]:
        """Abre um span manual e mede Qdrant ou LLM quando o nome coincide."""
        started = perf_counter()
        with self._tracer.start_as_current_span(name) as span:
            for key, value in (attributes or {}).items():
                span.set_attribute(key, value)
            try:
                yield _OtelSpanAttributes(span)
            except Exception:
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                self._record_dependency_latency(name, perf_counter() - started)

    def record_chat(self, observation: ChatObservation) -> None:
        """Conta o desfecho e publica as latências vistas pelo cliente."""
        log_chat(observation)
        labels = {"chat.outcome": observation.outcome.value}
        self._streams.add(1, labels)
        if observation.first_token_seconds is not None:
            self._first_token.record(observation.first_token_seconds, labels)
        if observation.duration_seconds is not None:
            self._duration.record(observation.duration_seconds, labels)

    def record_admission_rejected(
        self,
        *,
        request_id: str,
        session_fingerprint: str,
    ) -> None:
        """Conta HTTP 429 e registra a saturação sem a pergunta."""
        log_admission_rejected(
            request_id=request_id,
            session_fingerprint=session_fingerprint,
        )
        self._rejected.add(1)

    async def close(self) -> None:
        """Descarrega spans e métricas pendentes antes de encerrar o processo."""
        self._tracer_provider.shutdown()
        self._meter_provider.shutdown()

    def _record_dependency_latency(self, name: str, elapsed_seconds: float) -> None:
        """Guarda a latência das dependências que o span do Grafana não agrega sozinho."""
        if name == "qdrant":
            self._qdrant_latency.record(elapsed_seconds)
        elif name == "llm":
            self._llm_latency.record(elapsed_seconds)


def build_observability(
    settings: Settings,
    stream_gate: StreamGate,
    *,
    provider_factory: Callable[[Settings, StreamGate], OpenTelemetryObservability] | None = None,
) -> ObservabilityPort:
    """Exporta OTLP quando o endpoint existe; caso contrário só registra logs."""
    if not settings.otel_exporter_otlp_endpoint.strip():
        return LoggingObservability()
    factory = provider_factory or build_otlp_observability
    try:
        return factory(settings, stream_gate)
    except Exception:
        logger.exception("observability_export_disabled")
        return LoggingObservability()


def build_otlp_observability(
    settings: Settings,
    stream_gate: StreamGate,
) -> OpenTelemetryObservability:
    """Monta os provedores do SDK apontando para o endpoint OTLP configurado."""
    headers = parse_otlp_headers(settings.otel_exporter_otlp_headers.get_secret_value())
    resource = Resource.create({"service.name": settings.otel_service_name})
    sampler = ParentBased(TraceIdRatioBased(settings.otel_traces_sample_ratio))
    tracer_provider = TracerProvider(resource=resource, sampler=sampler)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=build_otlp_signal_endpoint(
                    settings.otel_exporter_otlp_endpoint,
                    "traces",
                ),
                headers=headers,
            )
        )
    )
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=build_otlp_signal_endpoint(
                settings.otel_exporter_otlp_endpoint,
                "metrics",
            ),
            headers=headers,
        )
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    return OpenTelemetryObservability(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        stream_gate=stream_gate,
    )


def parse_otlp_headers(value: str) -> dict[str, str]:
    """Converte o cabeçalho OTLP em um mapa e decodifica valores percentuais."""
    headers: dict[str, str] = {}
    for item in value.split(","):
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        name = key.strip()
        if name:
            headers[name] = unquote(raw_value.strip())
    return headers


def build_otlp_signal_endpoint(base: str, signal: str) -> str:
    """Anexa o caminho do sinal OTLP a partir da URL base do Grafana."""
    normalized = base.strip().rstrip("/")
    for suffix in _SIGNAL_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return f"{normalized}/v1/{signal}"
