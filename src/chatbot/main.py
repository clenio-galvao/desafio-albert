"""Ponto de entrada HTTP da aplicação."""

import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chatbot.adapters.inbound.api import router
from chatbot.adapters.inbound.web import router as web_router
from chatbot.bootstrap import ApplicationContainer, build_container
from chatbot.config import Settings, split_unique_csv


def create_app(
    *,
    container: ApplicationContainer | None = None,
    cors_origins: Sequence[str] | None = None,
) -> FastAPI:
    """Cria a aplicação sem efeitos colaterais para facilitar testes."""
    origins = (
        tuple(cors_origins)
        if cors_origins is not None
        else split_unique_csv(os.getenv("CORS_ORIGINS", ""))
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Compõe o container na subida e fecha clientes na descida."""
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
    if origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type"],
        )
    application.include_router(router)
    application.include_router(web_router)

    return application


app = create_app()


def run_server(**kwargs: Any) -> None:
    """Inicia o servidor quando executado pelo script instalado."""
    uvicorn.run("chatbot.main:app", host="0.0.0.0", port=8000, **kwargs)


if __name__ == "__main__":
    run_server()
