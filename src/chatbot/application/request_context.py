"""Identificador da requisição corrente, visível aos logs sem depender do HTTP."""

from contextvars import ContextVar, Token

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def bind_request_id(request_id: str) -> Token[str]:
    """Fixa o identificador da requisição no contexto assíncrono atual."""
    return _request_id.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    """Restaura o identificador anterior ao sair da requisição."""
    _request_id.reset(token)


def current_request_id() -> str:
    """Devolve o identificador corrente ou vazio fora de uma requisição."""
    return _request_id.get()
