"""Erros que representam violações das regras do domínio."""


class DomainError(ValueError):
    """Erro base para regras de negócio inválidas."""


class EmptyContentError(DomainError):
    """Uma mensagem ou trecho não possui conteúdo útil."""


class InvalidPageError(DomainError):
    """O número de página informado não é válido."""


class InvalidChunkPositionError(DomainError):
    """A posição do trecho dentro da página não é válida."""


class SessionLimitError(DomainError):
    """A sessão atingiu o limite configurado de mensagens."""
