"""Rotas HTTP finas que delegam regras aos casos de uso."""

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from time import perf_counter
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from chatbot.adapters.inbound.api.request_id import resolve_request_id
from chatbot.adapters.inbound.api.schemas import ChatBody, HealthResponse, ModelsResponse
from chatbot.adapters.inbound.api.sse import encode_chat_event, encode_error
from chatbot.application.exceptions import ApplicationError, ChatValidationError
from chatbot.application.models import ChatEvent, ChatEventType, ChatRequest
from chatbot.application.observability import ChatObservation, ChatOutcome, fingerprint_session
from chatbot.application.ports import ApplicationServices
from chatbot.application.request_context import current_request_id

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

    request_id = current_request_id() or resolve_request_id(
        request.headers.get("x-request-id")
    )
    session_fingerprint = fingerprint_session(body.session_id)
    admitted = await container.stream_gate.try_acquire()
    if not admitted:
        container.observability.record_admission_rejected(
            request_id=request_id,
            session_fingerprint=session_fingerprint,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="muitas respostas em andamento; tente novamente em instantes",
        )

    async def encode_sse_events() -> AsyncIterator[str]:
        """Serializa o caso de uso em eventos SSE e libera o gate ao terminar."""
        observed = _StreamObservation()
        stream = container.chat.stream(chat_request)
        try:
            async for event in _iter_timed_chat_events(
                request,
                stream,
                container.stream_timeout_seconds,
            ):
                observed.note(event)
                yield encode_chat_event(event)
        except TimeoutError:
            observed.outcome = ChatOutcome.TIMEOUT
            logger.warning(
                "chat_stream_timeout",
                extra={"session_fingerprint": session_fingerprint},
            )
            yield encode_error("tempo esgotado ao gerar a resposta.")
        except asyncio.CancelledError:
            observed.outcome = ChatOutcome.DISCONNECTED
            raise
        except ApplicationError:
            observed.outcome = ChatOutcome.ERROR
            logger.exception(
                "chat_application_error",
                extra={"session_fingerprint": session_fingerprint},
            )
            yield encode_error("Não foi possível concluir a resposta.")
        except Exception:
            observed.outcome = ChatOutcome.ERROR
            logger.exception(
                "chat_unexpected_error",
                extra={"session_fingerprint": session_fingerprint},
            )
            yield encode_error("Erro interno ao gerar a resposta.")
        finally:
            try:
                container.observability.record_chat(
                    observed.as_observation(
                        request_id=request_id,
                        session_fingerprint=session_fingerprint,
                        model=body.model,
                    )
                )
            finally:
                await container.stream_gate.release()

    return StreamingResponse(
        encode_sse_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )


@dataclass
class _StreamObservation:
    """Acumula sinais operacionais enquanto os eventos SSE são enviados."""

    outcome: ChatOutcome = ChatOutcome.DISCONNECTED
    citation_count: int = 0
    best_score: float | None = None
    first_token_seconds: float | None = None
    started: float = field(default_factory=perf_counter)
    saw_token: bool = False

    def note(self, event: ChatEvent) -> None:
        """Atualiza contagem, score e desfecho a partir de um evento do caso de uso."""
        if event.type is ChatEventType.METADATA:
            self.citation_count = len(event.citations)
            self.best_score = event.best_score
            return
        if event.type is ChatEventType.TOKEN and not self.saw_token:
            self.saw_token = True
            self.first_token_seconds = perf_counter() - self.started
            return
        if event.type is ChatEventType.DONE:
            self.outcome = (
                ChatOutcome.REFUSED if self.citation_count == 0 else ChatOutcome.COMPLETED
            )

    def as_observation(
        self,
        *,
        request_id: str,
        session_fingerprint: str,
        model: str,
    ) -> ChatObservation:
        """Fecha a medição do stream para o adapter de telemetria."""
        return ChatObservation(
            request_id=request_id,
            session_fingerprint=session_fingerprint,
            model=model,
            outcome=self.outcome,
            citation_count=self.citation_count,
            best_score=self.best_score,
            first_token_seconds=self.first_token_seconds,
            duration_seconds=perf_counter() - self.started,
        )


async def _iter_timed_chat_events(
    request: Request,
    stream: AsyncGenerator[ChatEvent, None],
    timeout_seconds: float,
) -> AsyncIterator[ChatEvent]:
    """Aplica o teto de geração quando configurado; zero deixa o stream sem limite."""
    events = _iter_chat_events(request, stream)
    if timeout_seconds <= 0:
        async for event in events:
            yield event
        return
    async with asyncio.timeout(timeout_seconds):
        async for event in events:
            yield event


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
