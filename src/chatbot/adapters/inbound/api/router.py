"""Rotas HTTP finas que delegam regras aos casos de uso."""

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from chatbot.adapters.inbound.api.schemas import ChatBody, HealthResponse, ModelsResponse
from chatbot.adapters.inbound.api.sse import encode_chat_event, encode_error
from chatbot.application.exceptions import ApplicationError, ChatValidationError
from chatbot.application.models import ChatEvent, ChatRequest
from chatbot.application.ports import ApplicationServices

logger = logging.getLogger(__name__)
router = APIRouter()


def require_container(request: Request) -> ApplicationServices:
    """Obtém o container composto no lifespan; recusa a rota se ainda não houver."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return cast(ApplicationServices, container)


Container = Annotated[ApplicationServices, Depends(require_container)]


@router.get("/health/live", response_model=HealthResponse, tags=["health"])
async def liveness() -> HealthResponse:
    """Confirma que o processo HTTP está no ar, sem consultar dependências."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def readiness(container: Container) -> HealthResponse:
    """Exige a base de conhecimento pronta antes de aceitar tráfego."""
    try:
        ready = await container.readiness.execute()
    except Exception:
        logger.exception("readiness_check_failed")
        ready = False
    if not ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="base de conhecimento indisponível",
        )
    return HealthResponse(status="ready")


@router.get("/v1/models", response_model=ModelsResponse, tags=["chat"])
async def list_models(container: Container) -> ModelsResponse:
    """Expõe a allowlist de modelos sem revelar o provedor."""
    return ModelsResponse(models=container.models.execute())


@router.delete(
    "/v1/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["chat"],
)
async def delete_session(session_id: str, container: Container) -> Response:
    """Remove o histórico temporário da sessão informada."""
    await container.end_session.execute(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/v1/chat/stream", response_class=StreamingResponse, tags=["chat"])
async def stream_chat(
    body: ChatBody,
    request: Request,
    container: Container,
) -> StreamingResponse:
    """Valida, admite o stream e devolve tokens por SSE sem vazar erros internos."""
    chat_request = ChatRequest(
        session_id=body.session_id,
        message=body.message,
        model=body.model,
    )
    try:
        container.chat.validate(chat_request)
    except ChatValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    admitted = await container.stream_gate.try_acquire()
    if not admitted:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="muitas respostas em andamento; tente novamente em instantes",
        )

    async def encode_sse_events() -> AsyncIterator[str]:
        """Serializa o caso de uso em eventos SSE e libera o gate ao terminar."""
        stream = container.chat.stream(chat_request)
        try:
            timeout = container.stream_timeout_seconds
            if timeout > 0:
                async with asyncio.timeout(timeout):
                    async for event in _iter_chat_events(request, stream):
                        yield encode_chat_event(event)
            else:
                async for event in _iter_chat_events(request, stream):
                    yield encode_chat_event(event)
        except TimeoutError:
            logger.warning("chat_stream_timeout", extra={"session_id": body.session_id})
            yield encode_error("tempo esgotado ao gerar a resposta.")
        except asyncio.CancelledError:
            raise
        except ApplicationError:
            logger.exception(
                "chat_application_error",
                extra={"session_id": body.session_id},
            )
            yield encode_error("Não foi possível concluir a resposta.")
        except Exception:
            logger.exception(
                "chat_unexpected_error",
                extra={"session_id": body.session_id},
            )
            yield encode_error("Erro interno ao gerar a resposta.")
        finally:
            await container.stream_gate.release()

    return StreamingResponse(
        encode_sse_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _iter_chat_events(
    request: Request,
    stream: AsyncGenerator[ChatEvent, None],
) -> AsyncIterator[ChatEvent]:
    """Encaminha eventos até o cliente desconectar e fecha o gerador do caso de uso."""
    try:
        async for event in stream:
            if await request.is_disconnected():
                return
            yield event
    finally:
        await stream.aclose()
