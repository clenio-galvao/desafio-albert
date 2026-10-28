from collections.abc import AsyncGenerator
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

from chatbot.adapters.outbound.load_doubles import LoadLLM
from chatbot.application import ChatEvent, ChatEventType, ChatRequest
from chatbot.application.use_cases import ModelCatalog
from chatbot.bootstrap import ApplicationContainer, build_load_container
from chatbot.load_testing import (
    LIVE_REQUEST_CAP,
    LoadReport,
    StreamSample,
    build_client_timeout,
    collect_stream,
    is_local_target,
    percentile,
    resolve_request_budget,
    run_load,
)
from chatbot.main import create_app


def test_percentile_returns_none_for_empty_values() -> None:
    assert percentile([], 50) is None


def test_percentile_returns_single_value() -> None:
    assert percentile([10.0], 95) == 10.0


def test_percentile_interpolates_p50() -> None:
    assert percentile([10.0, 20.0, 30.0, 40.0], 50) == 25.0


def test_percentile_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="percentil"):
        percentile([1.0], 120)


@pytest.mark.parametrize(
    "target",
    ["http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]/"],
)
def test_is_local_target_recognizes_loopback(target: str) -> None:
    assert is_local_target(target) is True


def test_is_local_target_rejects_public_host() -> None:
    assert is_local_target("https://desafio-albert-chatbot.onrender.com") is False


def test_resolve_request_budget_keeps_local_volume() -> None:
    assert resolve_request_budget(target="http://127.0.0.1:8000", requests=100, live=False) == 100


def test_resolve_request_budget_rejects_zero_requests() -> None:
    with pytest.raises(ValueError, match="maior que zero"):
        resolve_request_budget(target="http://127.0.0.1", requests=0, live=False)


def test_resolve_request_budget_caps_remote_url() -> None:
    with pytest.raises(ValueError, match=str(LIVE_REQUEST_CAP)):
        resolve_request_budget(
            target="https://desafio-albert-chatbot.onrender.com",
            requests=6,
            live=False,
        )


def test_resolve_request_budget_allows_published_profile_within_cap() -> None:
    assert (
        resolve_request_budget(
            target="https://desafio-albert-chatbot.onrender.com",
            requests=3,
            live=True,
        )
        == 3
    )


def test_load_report_summarizes_errors_and_percentiles() -> None:
    report = LoadReport(
        target="asgi://load-doubles",
        users=2,
        requests=3,
        samples=(
            StreamSample(200, 10.0, 20.0, True),
            StreamSample(200, 30.0, 40.0, True),
            StreamSample(429, None, 5.0, False, error="busy"),
        ),
    )

    payload = report.as_dict()
    assert payload["error_ratio"] == 0.3333
    assert payload["completed_ratio"] == 0.6667
    assert payload["status_counts"] == {200: 2, 429: 1}
    ttfb = cast(dict[str, float | None], payload["ttfb_ms"])
    assert ttfb["p50"] == 20.0


def test_empty_load_report_has_zero_ratios() -> None:
    report = LoadReport(target="asgi://load-doubles", users=1, requests=0, samples=())

    assert report.completed_ratio == 0.0
    assert report.error_ratio == 0.0
    empty_ttfb = cast(dict[str, float | None], report.as_dict()["ttfb_ms"])
    assert empty_ttfb["p50"] is None


async def test_collect_stream_records_http_error_body() -> None:
    app = create_app(container=build_load_container(token_delay_seconds=0.0))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://load.local",
        timeout=build_client_timeout(10),
    ) as client:
        rejected = await collect_stream(
            client,
            session_id="s",
            model="modelo-invalido",
            message="oi",
        )

    assert rejected.status_code == 422
    assert rejected.completed is False
    assert rejected.error


async def test_collect_stream_records_transport_error() -> None:
    async with AsyncClient(
        base_url="http://127.0.0.1:1",
        timeout=build_client_timeout(0.2),
    ) as client:
        failed = await collect_stream(
            client,
            session_id="s",
            model="azure/gpt-5-mini",
            message="oi",
        )

    assert failed.completed is False
    assert failed.error


async def test_collect_stream_records_sse_error_events() -> None:
    class ErrorChat:
        def validate(self, request: ChatRequest) -> None:
            del request

        async def stream(self, request: ChatRequest) -> AsyncGenerator[ChatEvent, None]:
            del request
            yield ChatEvent(type=ChatEventType.METADATA)
            yield ChatEvent(type=ChatEventType.TOKEN, content="parcial")
            raise RuntimeError("falha")

    app = create_app(
        container=ApplicationContainer(
            chat=ErrorChat(),
            models=ModelCatalog(["azure/gpt-5-mini"]),
            end_session=_ReadyEnd(),
            readiness=_ReadyEnd(),
            stream_timeout_seconds=5,
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://load.local",
        timeout=build_client_timeout(10),
    ) as client:
        sample = await collect_stream(
            client,
            session_id="s",
            model="azure/gpt-5-mini",
            message="oi",
        )

    assert sample.status_code == 200
    assert sample.error == "sse error"


class _ReadyEnd:
    async def execute(self, session_id: str | None = None) -> bool:
        del session_id
        return True


async def test_run_load_rejects_zero_users() -> None:
    with pytest.raises(ValueError, match="users"):
        await run_load(AsyncClient(), target="http://load.local", users=0, requests=1)


async def test_load_llm_yields_configured_tokens() -> None:
    llm = LoadLLM(tokens=("a", "b"), delay_seconds=0.0)

    tokens = [token async for token in llm.stream(model="model", messages=())]

    assert tokens == ["a", "b"]


async def test_load_llm_waits_between_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("chatbot.adapters.outbound.load_doubles.asyncio.sleep", fake_sleep)
    llm = LoadLLM(tokens=("a", "b"), delay_seconds=0.001)

    tokens = [token async for token in llm.stream(model="model", messages=())]

    assert tokens == ["a", "b"]
    assert waits == [0.001, 0.001]


async def test_run_load_against_fake_container_completes_streams() -> None:
    app = create_app(container=build_load_container(token_delay_seconds=0.0))
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://load.local",
        timeout=build_client_timeout(10),
    ) as client:
        report = await run_load(client, target="asgi://load-doubles", users=8, requests=16)

    assert report.completed_ratio == 1.0
    assert report.error_ratio == 0.0
    assert report.status_counts == {200: 16}
    assert report.ttfb_percentile(95) is not None
