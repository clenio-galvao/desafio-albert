"""Telemetria local e exportação OpenTelemetry."""

from chatbot.adapters.outbound.telemetry.json_logging import configure_logging
from chatbot.adapters.outbound.telemetry.otlp import build_observability

__all__ = ["build_observability", "configure_logging"]
