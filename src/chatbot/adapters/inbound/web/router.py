"""Entrega a página estática sem expor configuração do backend."""

from importlib.resources import files

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)
DEMO_HTML = files("chatbot.adapters.inbound.web").joinpath("demo.html").read_text("utf-8")


@router.get("/demo", response_class=HTMLResponse)
async def demo() -> HTMLResponse:
    return HTMLResponse(DEMO_HTML)
