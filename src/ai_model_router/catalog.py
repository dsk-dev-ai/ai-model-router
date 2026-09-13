"""Curated catalog of models with pricing, capabilities, and latency hints.

Prices are list price per 1M tokens (USD) for input and output as of the
catalog snapshot; use them as *estimates* — always authoritative invoices come
from the provider. ``latency_hint`` is a relative 1-5 score (lower = faster).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GOOGLE = "google"
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_MOCK = "mock"


@dataclass(frozen=True)
class Model:
    id: str
    provider: str
    price_in: float
    price_out: float
    ctx: int
    latency_hint: int
    capabilities: frozenset[str]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["capabilities"] = sorted(self.capabilities)
        return data


def _cap(*names: str) -> frozenset[str]:
    return frozenset(names)


MODEL_CATALOG: dict[str, Model] = {
    # OpenAI
    "gpt-4o": Model(
        "gpt-4o",
        PROVIDER_OPENAI,
        price_in=2.50,
        price_out=10.00,
        ctx=128_000,
        latency_hint=3,
        capabilities=_cap("tools", "vision", "json"),
    ),
    "gpt-4o-mini": Model(
        "gpt-4o-mini",
        PROVIDER_OPENAI,
        price_in=0.15,
        price_out=0.60,
        ctx=128_000,
        latency_hint=2,
        capabilities=_cap("tools", "vision", "json"),
    ),
    "gpt-3.5-turbo": Model(
        "gpt-3.5-turbo",
        PROVIDER_OPENAI,
        price_in=0.50,
        price_out=1.50,
        ctx=16_000,
        latency_hint=1,
        capabilities=_cap("tools", "json"),
    ),
    # Anthropic
    "claude-sonnet-4-20250514": Model(
        "claude-sonnet-4-20250514",
        PROVIDER_ANTHROPIC,
        price_in=3.00,
        price_out=15.00,
        ctx=200_000,
        latency_hint=3,
        capabilities=_cap("tools", "vision", "json"),
    ),
    "claude-3-5-haiku": Model(
        "claude-3-5-haiku",
        PROVIDER_ANTHROPIC,
        price_in=0.80,
        price_out=4.00,
        ctx=200_000,
        latency_hint=2,
        capabilities=_cap("tools", "vision"),
    ),
    # Google
    "gemini-2.0-flash": Model(
        "gemini-2.0-flash",
        PROVIDER_GOOGLE,
        price_in=0.10,
        price_out=0.40,
        ctx=1_048_576,
        latency_hint=2,
        capabilities=_cap("tools", "vision", "json", "long-context"),
    ),
    "gemini-1.5-pro": Model(
        "gemini-1.5-pro",
        PROVIDER_GOOGLE,
        price_in=1.25,
        price_out=5.00,
        ctx=2_000_000,
        latency_hint=4,
        capabilities=_cap("tools", "vision", "json", "long-context"),
    ),
    # OpenRouter (any OpenAI-compatible provider)
    "openrouter:meta-llama/llama-3.3-70b-instruct": Model(
        "openrouter:meta-llama/llama-3.3-70b-instruct",
        PROVIDER_OPENROUTER,
        price_in=0.15,
        price_out=0.30,
        ctx=131_000,
        latency_hint=2,
        capabilities=_cap("json"),
    ),
    "openrouter:deepseek/deepseek-chat": Model(
        "openrouter:deepseek/deepseek-chat",
        PROVIDER_OPENROUTER,
        price_in=0.14,
        price_out=0.28,
        ctx=64_000,
        latency_hint=1,
        capabilities=_cap("json"),
    ),
    # Deterministic offline provider (dev/tests)
    "mock/echo": Model(
        "mock/echo",
        PROVIDER_MOCK,
        price_in=0.0,
        price_out=0.0,
        ctx=1_000_000,
        latency_hint=1,
        capabilities=_cap("tools", "json"),
    ),
}


def list_models() -> list[dict[str, object]]:
    """All catalog entries, sorted by provider then id."""
    return [m.to_dict() for m in sorted(MODEL_CATALOG.values(), key=lambda m: m.id)]
