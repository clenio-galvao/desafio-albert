"""Correlação HTTP por X-Request-ID sem consumir o corpo SSE."""

import re
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from chatbot.application.request_context import bind_request_id, reset_request_id

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def resolve_request_id(candidate: str | None) -> str:
    """Aceita um identificador seguro ou gera outro, para não quebrar o log."""
    if candidate and _REQUEST_ID.fullmatch(candidate.strip()):
        return candidate.strip()
    return uuid4().hex


class RequestIdMiddleware:
    """Propaga ou gera X-Request-ID em qualquer resposta, inclusive streaming."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Grava o identificador no contexto e no cabeçalho de resposta."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        request_id = resolve_request_id(_header(scope, b"x-request-id"))
        scope.setdefault("state", {})["request_id"] = request_id
        token = bind_request_id(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["x-request-id"] = request_id
            await send(message)

        try:
            await self._app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)


def _header(scope: Scope, name: bytes) -> str | None:
    """Lê um cabeçalho cru do scope ASGI."""
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return bytes(value).decode("latin-1")
    return None
