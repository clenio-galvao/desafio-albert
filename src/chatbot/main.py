"""Ponto de entrada HTTP da aplicação."""

import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatbot.adapters.inbound.api import router
from chatbot.bootstrap import ApplicationContainer, build_container
from chatbot.config import Settings


def create_app(
    *,
    container: ApplicationContainer | None = None,
    cors_origins: Sequence[str] = (),
) -> FastAPI:
    """Cria a aplicação sem efeitos colaterais para facilitar testes."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_container = container or build_container(Settings())
        application.state.container = active_container
        try:
            yield
        finally:
            await active_container.close()

    application = FastAPI(
        title="Desafio Albert — Chatbot RAG",
        description="API de chatbot fundamentada em uma base de saúde mental.",
        version="0.1.0",
        lifespan=lifespan,
    )
    if container is not None:
        application.state.container = container
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type"],
        )
    application.include_router(router)

    return application


app = create_app(
    cors_origins=tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    )
)


def run(**kwargs: Any) -> None:
    """Inicia o servidor quando executado pelo script instalado."""
    uvicorn.run("chatbot.main:app", host="0.0.0.0", port=8000, **kwargs)


if __name__ == "__main__":
    run()
