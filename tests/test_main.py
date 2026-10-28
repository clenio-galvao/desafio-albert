from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from chatbot.bootstrap import ApplicationContainer
from chatbot.main import create_app, run_server


async def test_liveness_returns_ok() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_openapi_exposes_service_metadata() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"] == {
        "title": "Desafio Albert — Chatbot RAG",
        "description": "API de chatbot fundamentada em uma base de saúde mental.",
        "version": "0.1.0",
    }


def test_run_server_starts_uvicorn() -> None:
    with patch("chatbot.main.uvicorn.run") as uvicorn_run:
        run_server(reload=True)

    uvicorn_run.assert_called_once_with(
        "chatbot.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


async def test_lifespan_exposes_and_closes_injected_container() -> None:
    container = MagicMock(spec=ApplicationContainer)
    close = AsyncMock()
    container.close = close
    application = create_app(container=container)

    async with application.router.lifespan_context(application):
        assert application.state.container is container

    close.assert_awaited_once()
