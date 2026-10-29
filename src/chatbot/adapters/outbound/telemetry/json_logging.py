"""Logs JSON no stdout, sem texto da conversa."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from chatbot.application.observability import ChatObservation
from chatbot.application.request_context import current_request_id

_HANDLER_NAME = "chatbot-json"
_SAFE_FIELDS = frozenset(
    {
        "session_fingerprint",
        "chat_model",
        "outcome",
        "citation_count",
        "best_score",
        "first_token_seconds",
        "duration_seconds",
    }
)
logger = logging.getLogger("chatbot.observability")


class JsonLogFormatter(logging.Formatter):
    """Serializa cada registro em uma linha JSON com correlação segura."""

    def format(self, record: logging.LogRecord) -> str:
        """Monta o JSON operacional, incluindo trace apenas quando existe."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = current_request_id() or getattr(record, "request_id", "")
        if request_id:
            payload["request_id"] = request_id
        payload.update(_trace_ids())
        for key in _SAFE_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level_name: str) -> None:
    """Aplica o nível configurado e garante um handler JSON no processo."""
    level = _resolve_level(level_name)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        if handler.get_name() == _HANDLER_NAME:
            handler.setLevel(level)
            return
    handler = logging.StreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setLevel(level)
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)


def log_chat(observation: ChatObservation) -> None:
    """Registra o desfecho do stream só com campos operacionais."""
    logger.info("chat_stream", extra=_chat_fields(observation))


def log_admission_rejected(*, request_id: str, session_fingerprint: str) -> None:
    """Registra saturação do gate sem o texto da pergunta."""
    logger.warning(
        "chat_admission_rejected",
        extra={
            "request_id": request_id,
            "session_fingerprint": session_fingerprint,
            "outcome": "rejected",
        },
    )


def _chat_fields(observation: ChatObservation) -> dict[str, object]:
    """Seleciona campos numéricos e de desfecho para o log."""
    fields: dict[str, object] = {
        "session_fingerprint": observation.session_fingerprint,
        "chat_model": observation.model,
        "outcome": observation.outcome.value,
        "citation_count": observation.citation_count,
    }
    if observation.best_score is not None:
        fields["best_score"] = observation.best_score
    if observation.first_token_seconds is not None:
        fields["first_token_seconds"] = observation.first_token_seconds
    if observation.duration_seconds is not None:
        fields["duration_seconds"] = observation.duration_seconds
    return fields


def _trace_ids() -> dict[str, str]:
    """Lê o intervalo corrente para correlacionar o log com o Grafana."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
    }


def _resolve_level(level_name: str) -> int:
    """Traduz o nome do nível e cai em INFO quando o valor é desconhecido."""
    level = logging.getLevelNamesMapping().get(level_name.upper())
    if isinstance(level, int):
        return level
    return logging.INFO
