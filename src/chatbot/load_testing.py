"""Cliente de carga para streams SSE, sem Locust nem chamadas pagas por padrão."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

from httpx import AsyncClient, Timeout

LIVE_REQUEST_CAP = 5
DEFAULT_MODEL = "azure/gpt-5-mini"
DEFAULT_MESSAGE = "O que é escuta terapêutica?"
_MAX_ERROR_BODY_CHARS = 200


@dataclass(frozen=True, slots=True)
class StreamSample:
    """Resultado de um único stream SSE medido pelo cliente de carga."""

    status_code: int
    time_to_first_token_ms: float | None
    duration_ms: float
    completed: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class LoadReport:
    """Agrega amostras de carga em razões, contagens e percentis."""

    target: str
    users: int
    requests: int
    samples: tuple[StreamSample, ...]

    @property
    def completed_ratio(self) -> float:
        """Fração de streams que receberam o evento `done`."""
        if not self.samples:
            return 0.0
        return sum(sample.completed for sample in self.samples) / len(self.samples)

    @property
    def error_ratio(self) -> float:
        """Fração de streams com HTTP de erro, evento `error` ou sem `done`."""
        if not self.samples:
            return 0.0
        errors = sum(
            1
            for sample in self.samples
            if sample.error or sample.status_code >= 400 or not sample.completed
        )
        return errors / len(self.samples)

    @property
    def status_counts(self) -> dict[int, int]:
        """Conta códigos HTTP observados, ordenados pelo status."""
        counts: dict[int, int] = {}
        for sample in self.samples:
            counts[sample.status_code] = counts.get(sample.status_code, 0) + 1
        return dict(sorted(counts.items()))

    def ttfb_percentile(self, percent: float) -> float | None:
        """Percentil do tempo até o primeiro token, ignorando streams sem token."""
        return percentile(
            [
                sample.time_to_first_token_ms
                for sample in self.samples
                if sample.time_to_first_token_ms is not None
            ],
            percent,
        )

    def duration_percentile(self, percent: float) -> float | None:
        """Percentil da duração total de cada stream."""
        return percentile([sample.duration_ms for sample in self.samples], percent)

    def as_dict(self) -> dict[str, object]:
        """Serializa o relatório no formato impresso pelo script de carga."""
        return {
            "target": self.target,
            "users": self.users,
            "requests": self.requests,
            "completed_ratio": round(self.completed_ratio, 4),
            "error_ratio": round(self.error_ratio, 4),
            "status_counts": self.status_counts,
            "ttfb_ms": {
                "p50": _round_ms(self.ttfb_percentile(50)),
                "p95": _round_ms(self.ttfb_percentile(95)),
            },
            "duration_ms": {
                "p50": _round_ms(self.duration_percentile(50)),
                "p95": _round_ms(self.duration_percentile(95)),
            },
        }


def percentile(values: Sequence[float], percent: float) -> float | None:
    """Interpola o percentil informado ou devolve None quando não há amostras."""
    if not values:
        return None
    if not 0 <= percent <= 100:
        raise ValueError("percentil deve estar entre 0 e 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percent / 100)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def is_local_target(target: str) -> bool:
    """Identifica hosts de loopback para não aplicar o teto da cota publicada."""
    host = urlparse(target).hostname or target
    return host in {"127.0.0.1", "localhost", "::1"}


def resolve_request_budget(*, target: str, requests: int, live: bool) -> int:
    """Limita o volume remoto para não esgotar a cota do gateway."""
    if requests < 1:
        raise ValueError("requests deve ser maior que zero")
    remote = live or not is_local_target(target)
    if remote and requests > LIVE_REQUEST_CAP:
        raise ValueError(
            f"perfil publicado limita-se a {LIVE_REQUEST_CAP} requisições para preservar a cota"
        )
    return requests


async def collect_stream(
    client: AsyncClient,
    *,
    session_id: str,
    model: str,
    message: str,
) -> StreamSample:
    """Mede um POST `/v1/chat/stream` até `done`, erro HTTP ou falha de transporte."""
    started = time.perf_counter()
    first_token_at: float | None = None
    completed = False
    status_code = 0
    error: str | None = None
    try:
        async with client.stream(
            "POST",
            "/v1/chat/stream",
            json={"session_id": session_id, "message": message, "model": model},
        ) as response:
            status_code = response.status_code
            if status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")
                error = body[:_MAX_ERROR_BODY_CHARS] or f"HTTP {status_code}"
            else:
                async for line in response.aiter_lines():
                    if first_token_at is None and line.startswith("event: token"):
                        first_token_at = (time.perf_counter() - started) * 1000
                    if line.startswith("event: done"):
                        completed = True
                    if line.startswith("event: error"):
                        error = "sse error"
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        status_code = status_code or 0

    duration_ms = (time.perf_counter() - started) * 1000
    ttfb = first_token_at
    return StreamSample(
        status_code=status_code,
        time_to_first_token_ms=ttfb,
        duration_ms=duration_ms,
        completed=completed,
        error=error,
    )


async def run_load(
    client: AsyncClient,
    *,
    target: str,
    users: int,
    requests: int,
    model: str = DEFAULT_MODEL,
    message: str = DEFAULT_MESSAGE,
) -> LoadReport:
    """Dispara streams concorrentes limitados pelo número de usuários simultâneos."""
    if users < 1:
        raise ValueError("users deve ser maior que zero")
    limiter = asyncio.Semaphore(users)

    async def collect_one_stream(index: int) -> StreamSample:
        """Executa um stream isolado respeitando o semáforo de usuários."""
        async with limiter:
            return await collect_stream(
                client,
                session_id=f"load-{index}",
                model=model,
                message=message,
            )

    samples = await asyncio.gather(
        *(collect_one_stream(index) for index in range(requests))
    )
    return LoadReport(
        target=target,
        users=users,
        requests=requests,
        samples=tuple(samples),
    )


def build_client_timeout(seconds: float = 60.0) -> Timeout:
    """Timeout HTTP único para conexão, leitura e pool do cliente de carga."""
    return Timeout(seconds)


def _round_ms(value: float | None) -> float | None:
    """Arredonda milissegundos para o relatório JSON, preservando ausência."""
    if value is None:
        return None
    return round(value, 2)
