"""Erros dos casos de uso, independentes do transporte HTTP."""


class ApplicationError(Exception):
    """Erro base da camada de aplicação."""


class UnsupportedModelError(ApplicationError):
    """O modelo solicitado não pertence à allowlist."""
