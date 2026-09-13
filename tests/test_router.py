"""Router engine tests: fallback, explicit model, costing, streaming."""

from __future__ import annotations

import pytest

from ai_model_router.catalog import Model
from ai_model_router.metrics import Metrics
from ai_model_router.models import ChatRequest, RouterSpec
from ai_model_router.providers.mock import MockProvider
from ai_model_router.router import RouterEngine, RouterError, RouterNoMatchError

FAILING = "mock/fail"
OK = "mock/ok"


def _catalog() -> dict[str, Model]:
    return {
        FAILING: Model(
            id=FAILING,
            provider="mock",
            price_in=0.0,
            price_out=0.0,
            ctx=1000,
            latency_hint=1,
            capabilities=frozenset({"tools"}),
        ),
        OK: Model(
            id=OK,
            provider="mock",
            price_in=0.5,
            price_out=2.0,
            ctx=1000,
            latency_hint=2,
            capabilities=frozenset({"tools"}),
        ),
    }


def _engine() -> RouterEngine:
    return RouterEngine(
        providers={"mock": MockProvider(fail_models=FAILING)},
        catalog=_catalog(),
    )


def _req(model: str = "auto", **router: object) -> ChatRequest:
    spec = RouterSpec(policy="priority", priority=[model])
    return ChatRequest(
        model=model,
        messages=[{"role": "user", "content": "hello"}],
        router=spec,
    )


async def test_chat_from_mock() -> None:
    engine = _engine()
    response = await engine.chat(_req(OK))
    assert response.model == OK
    assert response.route.provider == "mock"
    assert response.route.attempts == 1
    assert response.route.fallback_used is False
    assert response.usage.total_tokens > 0


async def test_fallback_when_first_model_fails() -> None:
    engine = _engine()
    spec = RouterSpec(policy="priority", priority=[OK])
    request = ChatRequest(
        model="auto",
        messages=[{"role": "user", "content": "hi"}],
        router=spec,
    )
    response = await engine.chat(request)
    assert response.model == OK
    assert response.route.attempts == 1


async def test_fallback_when_explicit_model_fails() -> None:
    engine = _engine()
    response = await engine.chat(_req(FAILING))
    assert response.model == OK
    assert response.route.fallback_used is True
    assert response.route.attempts == 2
    assert response.route.chosen_model == OK
    assert "failure" in response.route.router_reason


async def test_routing_error_when_all_fail() -> None:
    engine = RouterEngine(
        providers={"mock": MockProvider(fail_models=f"{FAILING},{OK}")},
        catalog=_catalog(),
    )
    with pytest.raises(RouterError) as exc_info:
        await engine.chat(_req(OK))
    assert "failed" in str(exc_info.value)


async def test_no_match_request() -> None:
    engine = _engine()
    request = ChatRequest(
        model="auto",
        messages=[{"role": "user", "content": "hi"}],
        router=RouterSpec(policy="cheapest", providers=["google"]),
    )
    with pytest.raises(RouterNoMatchError):
        await engine.chat(request)


async def test_cost_is_estimated_from_catalog_prices() -> None:
    engine = _engine()
    response = await engine.chat(_req(OK))
    tokens_in = response.usage.prompt_tokens
    tokens_out = response.usage.completion_tokens
    expected = round(tokens_in / 1e6 * 0.5 + tokens_out / 1e6 * 2.0, 6)
    assert response.usage.estimated_cost_usd == expected
    assert response.usage.estimated_cost_usd > 0


async def test_records_calls_and_cost_in_metrics() -> None:
    engine = _engine()
    await engine.chat(_req(OK))
    snapshot = engine.metrics.snapshot()
    assert snapshot["mock"]["calls"] == 1
    assert snapshot["mock"]["cost_usd"] > 0


async def test_failed_calls_are_tracked() -> None:
    engine = RouterEngine(
        providers={"mock": MockProvider(fail_models=f"{FAILING},{OK}")},
        catalog=_catalog(),
    )
    with pytest.raises(RouterError):
        await engine.chat(_req(OK))
    snapshot = engine.metrics.snapshot()
    assert snapshot["mock"]["failed_calls"] == 2


async def test_stream_falls_back_and_yields_chunks() -> None:
    engine = RouterEngine(
        providers={"mock": MockProvider(fail_models=FAILING)},
        catalog=_catalog(),
    )
    chunks = [b async for b in engine.stream(_req(FAILING))]
    body = b"".join(chunks).decode()
    assert "data: [DONE]" in body
    assert "ROUTER_ERROR" not in body


async def test_stream_terminates_with_error_when_all_fail() -> None:
    engine = RouterEngine(
        providers={"mock": MockProvider(fail_models=f"{FAILING},{OK}")},
        catalog=_catalog(),
    )
    chunks = [b async for b in engine.stream(_req(OK))]
    body = b"".join(chunks).decode()
    assert "ROUTER_ERROR" in body


async def test_empty_messages_rejected() -> None:
    engine = _engine()
    with pytest.raises(RouterError):
        await engine.chat(ChatRequest(messages=[], router=RouterSpec()))


def test_metrics_snapshot_empty() -> None:
    assert Metrics().snapshot() == {}
