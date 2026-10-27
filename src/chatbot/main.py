"""Ponto de entrada HTTP da aplicação."""

from typing import Any

import uvicorn
from fastapi import FastAPI


def create_app() -> FastAPI:
    """Cria a aplicação sem efeitos colaterais para facilitar testes."""
    application = FastAPI(
        title="Desafio Albert — Chatbot RAG",
        description="API de chatbot fundamentada em uma base de saúde mental.",
        version="0.1.0",
    )

    @application.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()


def run(**kwargs: Any) -> None:
    """Inicia o servidor quando executado pelo script instalado."""
    uvicorn.run("chatbot.main:app", host="0.0.0.0", port=8000, **kwargs)


if __name__ == "__main__":
    run()
