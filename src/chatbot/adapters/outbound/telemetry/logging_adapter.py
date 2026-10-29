"""Telemetria local: logs JSON e intervalos sem exportação."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from chatbot.adapters.outbound.telemetry.json_logging import log_admission_rejected, log_chat
from chatbot.application.observability import (
    ChatObservation,
    NullObservability,
    SpanAttributeWriter,
)


class LoggingObservability:
    """Grava desfechos no stdout e não abre intervalos exportáveis."""

    def __init__(self) -> None:
        self._spans = NullObservability()

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> Iterator[SpanAttributeWriter]:
        """Delega o intervalo vazio para não alterar o fluxo do chat."""
        with self._spans.start_span(name, attributes) as span:
            yield span

    def record_chat(self, observation: ChatObservation) -> None:
        """Emite o log operacional do stream."""
        log_chat(observation)

    def record_admission_rejected(
        self,
        *,
        request_id: str,
        session_fingerprint: str,
    ) -> None:
        """Emite o log de saturação antes de o SSE abrir."""
        log_admission_rejected(
            request_id=request_id,
            session_fingerprint=session_fingerprint,
        )
