"""Executa o teste de carga local (fakes) ou o perfil mínimo publicado."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from chatbot.bootstrap import build_load_container
from chatbot.load_testing import (
    DEFAULT_MESSAGE,
    DEFAULT_MODEL,
    LIVE_REQUEST_CAP,
    build_client_timeout,
    resolve_request_budget,
    run_load,
)
from chatbot.main import create_app


@asynccontextmanager
async def load_client(target: str | None) -> AsyncIterator[tuple[str, AsyncClient]]:
    """Abre cliente HTTP remoto ou a API in-process com dublês de carga."""
    if target:
        async with AsyncClient(
            base_url=target.rstrip("/"),
            timeout=build_client_timeout(),
        ) as client:
            yield target.rstrip("/"), client
        return

    app = create_app(container=build_load_container())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://load.local",
        timeout=build_client_timeout(),
    ) as client:
        yield "asgi://load-doubles", client


async def run_load_test(args: argparse.Namespace) -> int:
    """Roda a carga, imprime o relatório e devolve código de saída pelo error_ratio."""
    live = bool(args.target)
    try:
        requests = resolve_request_budget(
            target=args.target or "http://127.0.0.1",
            requests=args.requests,
            live=live,
        )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    async with load_client(args.target) as (label, client):
        report = await run_load(
            client,
            target=label,
            users=args.users,
            requests=requests,
            model=args.model,
            message=args.message,
        )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    if live:
        print(
            f"perfil publicado limitado a {LIVE_REQUEST_CAP} requisições",
            file=sys.stderr,
        )
    return 0 if report.error_ratio == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    """Declara usuários, volume, modelo e alvo opcional da carga."""
    parser = argparse.ArgumentParser(
        description="Teste de carga do chat SSE. Sem --target usa LLM e retriever fake.",
    )
    parser.add_argument("--users", type=int, default=25, help="usuários simultâneos")
    parser.add_argument("--requests", type=int, default=100, help="total de streams")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument(
        "--target",
        default=None,
        help=(
            "URL publicada. Ativa o teto de "
            f"{LIVE_REQUEST_CAP} requisições para não esgotar a cota."
        ),
    )
    return parser


def main() -> None:
    """Ponto de entrada do script de carga."""
    raise SystemExit(asyncio.run(run_load_test(build_parser().parse_args())))


if __name__ == "__main__":
    main()
