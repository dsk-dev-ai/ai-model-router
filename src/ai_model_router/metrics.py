"""In-memory usage and spend tracking (MVP; no persistence)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from ai_model_router.models import RouteInfo, Usage


@dataclass
class ProviderStat:
    calls: int = 0
    failed_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    accrued_latency_ms: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.calls == 0:
            return 0.0
        return self.accrued_latency_ms / self.calls

    def to_dict(self) -> dict[str, float | int]:
        return {
            "calls": self.calls,
            "failed_calls": self.failed_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


@dataclass
class Metrics:
    _by_provider: dict[str, ProviderStat] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, provider: str, route: RouteInfo, usage: Usage) -> None:
        with self._lock:
            stat = self._by_provider.setdefault(provider, ProviderStat())
            stat.calls += 1
            stat.prompt_tokens += usage.prompt_tokens
            stat.completion_tokens += usage.completion_tokens
            stat.cost_usd += usage.estimated_cost_usd
            stat.accrued_latency_ms += route.latency_ms

    def record_failure(self, provider: str) -> ProviderStat:
        with self._lock:
            stat = self._by_provider.setdefault(provider, ProviderStat())
            stat.failed_calls += 1
            return stat

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            return {k: v.to_dict() for k, v in sorted(self._by_provider.items())}
