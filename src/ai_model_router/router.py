"""The routing engine: policy selection, provider call, error fallback, cost."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Final

from ai_model_router.catalog import MODEL_CATALOG, Model
from ai_model_router.metrics import Metrics
from ai_model_router.models import (
    ChatChoice,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    RouteInfo,
    Usage,
    new_response,
)
from ai_model_router.policy import rank_candidates
from ai_model_router.providers.base import Provider, ProviderError

OPENROUTER_PREFIX: Final = "openrouter:"


class RouterError(RuntimeError):
    """Request failed because no model could serve it."""


class RouterNoMatchError(RouterError):
    """Request constraints excluded every catalog model."""


class RouterEngine:
    def __init__(
        self,
        providers: dict[str, Provider] | None = None,
        catalog: dict[str, Model] | None = None,
    ) -> None:
        self.providers = providers or {}
        self.catalog = catalog or MODEL_CATALOG
        self.metrics = Metrics()

    # -- public -------------------------------------------------------------

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Route and run a non-streamed completion."""
        if not request.messages:
            raise RouterError("messages must not be empty")
        candidates, requested = self._resolve_candidates(request)
        if not candidates:
            raise RouterNoMatchError(self._no_match_message(request))

        spec = request.router
        last_error: str = ""
        attempts = 0
        for model in candidates:
            provider = self.providers.get(model.provider)
            if provider is None:
                self.metrics.record_failure(model.provider)
                last_error = f"provider '{model.provider}' is not configured"
                continue
            attempts += 1
            started = time.perf_counter()
            try:
                result = await provider.chat(request, model)
            except ProviderError as exc:
                elapsed_ms = self._ms(started)
                last_error = str(exc)
                self.metrics.record_failure(model.provider)
                if not spec.fallback:
                    break
                continue
            elapsed_ms = self._ms(started)

            usage = self._price(model, result.usage)
            route = RouteInfo(
                requested_model=requested,
                chosen_model=model.id,
                provider=model.provider,
                policy_used=spec.policy,
                attempts=attempts,
                fallback_used=attempts > 1,
                latency_ms=elapsed_ms,
                estimated_cost_usd=usage.estimated_cost_usd,
                router_reason=(
                    f"served by {model.provider} after {attempts - 1} failure(s)"
                    if attempts > 1
                    else "first-choice model"
                ),
            )
            self.metrics.record(model.provider, route, usage)
            response = new_response(model=model.id)
            response.choices = [
                ChatChoice(
                    message=ChatMessage(
                        role=result.role,
                        content=result.content,
                        tool_calls=result.raw.get("choices", [{}])[0]
                        .get("message", {})
                        .get("tool_calls")
                        if result.raw
                        else None,
                    ),
                    finish_reason=result.finish_reason,
                )
            ]
            response.usage = usage
            response.route = route
            return response

        raise RouterError(f"all {attempts} candidate(s) failed: {last_error}")

    async def stream(self, request: ChatRequest) -> AsyncIterator[bytes]:
        """Route and stream SSE bytes; falls back across candidates."""
        candidates, requested = self._resolve_candidates(request)
        if not candidates:
            yield f"data: {self._no_match_message(request)}\n\n".encode()
            return
        spec = request.router
        last_error = ""
        for model in candidates:
            provider = self.providers.get(model.provider)
            if provider is None:
                self.metrics.record_failure(model.provider)
                last_error = f"provider '{model.provider}' is not configured"
                continue
            started = time.perf_counter()
            try:
                gen = provider.stream(request, model)
                async for chunk in gen:
                    yield chunk
                self.metrics.record(
                    model.provider,
                    RouteInfo(
                        requested_model=requested,
                        chosen_model=model.id,
                        provider=model.provider,
                        policy_used=spec.policy,
                        attempts=1,
                        fallback_used=False,
                        latency_ms=self._ms(started),
                        router_reason="streamed response",
                    ),
                    Usage(),
                )
                return
            except ProviderError as exc:
                last_error = str(exc)
                self.metrics.record_failure(model.provider)
                if not spec.fallback:
                    break
                continue
            except Exception as exc:  # mid-stream failures terminate streaming
                last_error = str(exc)
                self.metrics.record_failure(model.provider)
                break
        yield f"data: [ROUTER_ERROR] {last_error}\n\n".encode()

    # -- internals ----------------------------------------------------------

    def _resolve_candidates(self, request: ChatRequest) -> tuple[list[Model], str]:
        spec = request.router
        requested = request.model or "auto"
        if requested in self.catalog:
            ordered = [self.catalog[requested]]
            for model in rank_candidates(self.catalog.values(), spec):
                if model.id != requested:
                    ordered.append(model)
            return ordered, requested
        return rank_candidates(self.catalog.values(), spec), "auto"

    def _no_match_message(self, request: ChatRequest) -> str:
        spec = request.router
        bits = [f"policy='{spec.policy}'"]
        if spec.requires:
            bits.append(f"requires={spec.requires}")
        if spec.providers:
            bits.append(f"providers={spec.providers}")
        if spec.max_cost_usd is not None:
            bits.append(f"max_cost_usd={spec.max_cost_usd}")
        return f"no model satisfies {', '.join(bits)}"

    @staticmethod
    def _price(model: Model, usage: Usage) -> Usage:
        cost = (
            usage.prompt_tokens / 1_000_000 * model.price_in
            + usage.completion_tokens / 1_000_000 * model.price_out
        )
        usage.estimated_cost_usd = round(cost, 6)
        return usage

    @staticmethod
    def _ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
