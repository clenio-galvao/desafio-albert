"""Fatos operacionais do chat, sem texto da conversa."""

import hashlib
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ChatOutcome(StrEnum):
    """Desfechos estáveis de um stream, usados em log e métrica."""

    COMPLETED = "completed"
    REFUSED = "refused"
    TIMEOUT = "timeout"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ChatObservation:
    """Resumo operacional de um stream já encerrado."""

    request_id: str
    session_fingerprint: str
    model: str
    outcome: ChatOutcome
    citation_count: int
    best_score: float | None = None
    first_token_seconds: float | None = None
    duration_seconds: float | None = None


class SpanAttributeWriter(Protocol):
    """Permite anotar o intervalo aberto sem conhecer o exportador."""

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        """Anexa um atributo operacional ao intervalo aberto."""
        ...


class _SilentSpan:
    """Ignora atributos quando não há telemetria ativa."""

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        """Descarta o atributo; a API continua sem backend."""
        return None


class NullObservability:
    """Descarta telemetria; usado em testes e quando o exportador falha."""

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: Mapping[str, str | int | float | bool] | None = None,
    ) -> Iterator[_SilentSpan]:
        """Não abre intervalo e não registra duração."""
        del name, attributes
        yield _SilentSpan()

    def record_chat(self, observation: ChatObservation) -> None:
        """Ignora o desfecho do stream."""
        del observation
        return None

    def record_admission_rejected(
        self,
        *,
        request_id: str,
        session_fingerprint: str,
    ) -> None:
        """Ignora a recusa de admissão."""
        del request_id, session_fingerprint
        return None


def fingerprint_session(session_id: str) -> str:
    """Resume a sessão para correlação sem gravar o identificador original."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]
