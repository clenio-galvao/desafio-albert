"""Caso de uso para expor e validar a allowlist de modelos."""

from collections.abc import Iterable

from chatbot.application.exceptions import UnsupportedModelError


class ModelCatalog:
    """Catálogo imutável compartilhado pelos casos de uso e pela API."""

    def __init__(self, models: Iterable[str]) -> None:
        normalized = tuple(dict.fromkeys(model.strip() for model in models if model.strip()))
        if not normalized:
            raise ValueError("ao menos um modelo deve ser configurado")
        self._models = normalized

    def execute(self) -> tuple[str, ...]:
        return self._models

    def ensure_supported(self, model: str) -> None:
        if model not in self._models:
            raise UnsupportedModelError(f"modelo não permitido: {model}")
