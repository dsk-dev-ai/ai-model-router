"""Semantic cache behavior and measured-latency routing."""

from __future__ import annotations

from ai_model_router.cache import make_cache_key, normalize_message, serialize_cacheable
from ai_model_router.catalog import Model
from ai_model_router.models import ChatRequest, RouterSpec
from ai_model_router.providers.mock import MockProvider
from ai_model_router.router import RouterEngine
from ai_model_router.storage import Storage

OK = "mock/ok"


def _model() -> Model:
    return Model(
        id=OK,
        provider="mock",
        price_in=1.0,
        price_out=1.0,
        ctx=1000,
        latency_hint=250,
        capabilities=frozenset(),
    )


def _engine() -> RouterEngine:
    storage = Storage()
    return RouterEngine(
        providers={"mock": MockProvider()},
        catalog={OK: _model()},
        storage=storage,
    )


def _request(content: str = "same question") -> ChatRequest:
    return ChatRequest(messages=[{"role": "user", "content": content}])


async def test_normalize_and_key_stability() -> None:
    assert normalize_message({"role": "user", "content": "  Hello  World "}) == normalize_message(
        {"role": "user", "content": "hello world"}
    )
    assert make_cache_key([{"role": "user", "content": "a"}]) != make_cache_key(
        [{"role": "user", "content": "b"}]
    )


async def test_second_call_hits_cache_and_is_free() -> None:
    engine = _engine()
    first = await engine.chat(_request("repeat me"), key_id=1)
    second = await engine.chat(_request("repeat me"), key_id=1)
    assert first.route.router_reason != "semantic cache hit"
    assert second.route.router_reason == "semantic cache hit"
    assert second.usage.estimated_cost_usd == 0.0
    assert second.usage.completion_tokens == first.usage.completion_tokens
    assert second.route.chosen_model == first.route.chosen_model
    summary = engine.storage.usage_summary()  # type: ignore[union-attr]
    assert summary["cached"] == 1


async def test_cache_disabled_per_request() -> None:
    engine = _engine()
    spec = RouterSpec(cache_enabled=False)
    first = await engine.chat(ChatRequest(messages=[{"role": "user", "content": "x"}], router=spec))
    second = await engine.chat(
        ChatRequest(messages=[{"role": "user", "content": "x"}], router=spec)
    )
    assert second.route.router_reason != "semantic cache hit"
    assert first.route.router_reason != "semantic cache hit"


async def test_different_content_not_cached() -> None:
    engine = _engine()
    await engine.chat(_request("question one"))
    second = await engine.chat(_request("question two"))
    assert second.route.router_reason != "semantic cache hit"


async def test_cache_payload_round_trip() -> None:
    payload = serialize_cacheable(
        model=OK, content="hi", finish_reason="stop", prompt_tokens=3, completion_tokens=1
    )
    assert payload["model"] == OK
    assert payload["content"] == "hi"


async def test_measured_latency_reorders_candidates() -> None:
    slow = Model(
        id="mock/slow",
        provider="mock",
        price_in=0,
        price_out=0,
        ctx=1000,
        latency_hint=1,
        capabilities=frozenset(),
    )
    fast = Model(
        id="mock/fast",
        provider="mock",
        price_in=0,
        price_out=0,
        ctx=1000,
        latency_hint=500,
        capabilities=frozenset(),
    )
    storage = Storage()
    storage.add_latency_sample("mock", "mock/slow", 900)
    storage.add_latency_sample("mock", "mock/fast", 10)
    storage.add_latency_sample("mock", "mock/fast", 20)
    engine = RouterEngine(
        providers={"mock": MockProvider()},
        catalog={slow.id: slow, fast.id: fast},
        storage=storage,
    )
    assert storage.measured_avg_ms()["mock/fast"] == 15.0
    candidates, _ = engine._resolve_candidates(
        ChatRequest(
            messages=[{"role": "user", "content": "hi"}], router=RouterSpec(policy="fastest")
        )
    )
    assert candidates[0].id == "mock/fast"
