"""Routing policy: order and filter candidate models, then pick one.

Policies:
- ``priority``   explicit ordered list (defaults to catalog order) — first
                 candidate that satisfies constraints wins.
- ``cheapest``   lowest combined input+output list price first.
- ``fastest``    lowest latency hint first.
"""

from __future__ import annotations

from collections.abc import Iterable

from ai_model_router.catalog import Model
from ai_model_router.models import RouterSpec

POLICIES = ("priority", "cheapest", "fastest")


def _capabilities_ok(model: Model, required: Iterable[str]) -> bool:
    return all(cap in model.capabilities for cap in required)


def _cost_ok(model: Model, max_cost_usd: float | None) -> bool:
    if max_cost_usd is None:
        return True
    return model.price_out <= max_cost_usd or model.price_in <= max_cost_usd


def _latency(model: Model, measured: dict[str, float]) -> float:
    return measured.get(model.id, model.latency_hint)


def _sort_key(
    model: Model,
    policy: str,
    priority: list[str],
    measured: dict[str, float],
) -> tuple[int, float]:
    if policy == "cheapest":
        return (0, model.price_in + model.price_out)
    if policy == "fastest":
        return (0, _latency(model, measured))
    try:
        index = priority.index(model.id)
    except ValueError:
        index = len(priority) + 10_000
    return (index, _latency(model, measured))


def rank_candidates(
    models: Iterable[Model],
    spec: RouterSpec,
    measured: dict[str, float] | None = None,
) -> list[Model]:
    """Filter by constraints and order candidates for this request."""
    required = set(spec.requires)
    allowed = set(spec.providers)
    wanted = list(spec.priority)
    measured = measured or {}
    candidates = [
        m
        for m in models
        if _capabilities_ok(m, required)
        and _cost_ok(m, spec.max_cost_usd)
        and (not allowed or m.provider in allowed)
    ]
    policy = spec.policy if spec.policy in POLICIES else "priority"
    return sorted(candidates, key=lambda m: _sort_key(m, policy, wanted, measured))


def pick_model(models: Iterable[Model], spec: RouterSpec) -> Model | None:
    """Return the single best candidate or ``None`` if nothing qualifies."""
    candidates = rank_candidates(models, spec)
    return candidates[0] if candidates else None
