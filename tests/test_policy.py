"""Policy unit tests: ordering, filtering, cost guardrails."""

from ai_model_router.catalog import Model
from ai_model_router.models import RouterSpec
from ai_model_router.policy import pick_model, rank_candidates


def _model(
    mid: str,
    provider: str,
    price_in: float,
    price_out: float,
    latency: int,
    caps: set[str] | None = None,
) -> Model:
    return Model(
        id=mid,
        provider=provider,
        price_in=price_in,
        price_out=price_out,
        ctx=1000,
        latency_hint=latency,
        capabilities=frozenset(caps or {"tools"}),
    )


CATALOG = [
    _model("exp", "openai", 10.0, 30.0, 5, {"tools"}),
    _model("cheap", "openai", 0.1, 0.3, 3, {"tools"}),
    _model("fast", "anthropic", 3.0, 9.0, 1, {"json"}),
]


def test_cheapest_policy() -> None:
    spec = RouterSpec(policy="cheapest")
    assert pick_model(CATALOG, spec).id == "cheap"  # type: ignore[union-attr]


def test_fastest_policy() -> None:
    spec = RouterSpec(policy="fastest")
    assert pick_model(CATALOG, spec).id == "fast"  # type: ignore[union-attr]


def test_priority_respects_explicit_order() -> None:
    spec = RouterSpec(policy="priority", priority=["fast", "exp", "cheap"])
    order = [m.id for m in rank_candidates(CATALOG, spec)]
    assert order[:3] == ["fast", "exp", "cheap"]


def test_requires_filters_capabilities() -> None:
    spec = RouterSpec(policy="cheapest", requires=["json"])
    order = [m.id for m in rank_candidates(CATALOG, spec)]
    assert "cheap" not in order
    assert order[0] == "fast"


def test_providers_filter() -> None:
    spec = RouterSpec(policy="cheapest", providers=["anthropic"])
    order = [m.id for m in rank_candidates(CATALOG, spec)]
    assert order == ["fast"]


def test_max_cost_winsnows_out_pricey_models() -> None:
    spec = RouterSpec(policy="priority", max_cost_usd=1.0)
    result = pick_model(CATALOG, spec)
    assert result is not None
    assert result.id == "cheap"


def test_no_match_returns_none() -> None:
    spec = RouterSpec(policy="cheapest", providers=["google"])
    assert pick_model(CATALOG, spec) is None


def test_unknown_policy_falls_back_to_priority() -> None:
    spec = RouterSpec(policy="bogus", priority=["exp"])
    assert pick_model(CATALOG, spec).id == "exp"  # type: ignore[union-attr]
