"""Erros dos casos de uso, independentes do transporte HTTP."""


class ApplicationError(Exception):
    """Erro base da camada de aplicação."""


class ChatValidationError(ApplicationError):
    """A solicitação de chat viola uma política da aplicação."""


class UnsupportedModelError(ChatValidationError):
    """O modelo solicitado não pertence à allowlist."""


class MessageTooLongError(ChatValidationError):
    """A mensagem ultrapassa o limite configurado pela aplicação."""


class EmptyGenerationError(ApplicationError):
    """O provedor encerrou o stream sem produzir uma resposta útil."""
