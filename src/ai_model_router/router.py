"""The routing engine: policy selection, provider call, error fallback, cost."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Final

from ai_model_router.cache import (
    is_cacheable,
    make_cache_key,
    serialize_cacheable,
)
from ai_model_router.catalog import MODEL_CATALOG, Model
from ai_model_router.guardrails import (
    messages_contain_injection,
    redact_messages,
    redact_text,
)
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
from ai_model_router.storage import Storage

OPENROUTER_PREFIX: Final = "openrouter:"


class RouterError(RuntimeError):
    """Request failed because no model could serve it."""


class RouterNoMatchError(RouterError):
    """Request constraints excluded every catalog model."""


class RouterBlockError(RouterError):
    """Request was rejected by a guardrail."""


class RouterEngine:
    def __init__(
        self,
        providers: dict[str, Provider] | None = None,
        catalog: dict[str, Model] | None = None,
        storage: Storage | None = None,
    ) -> None:
        self.providers = providers or {}
        self.catalog = catalog or MODEL_CATALOG
        self.storage = storage
        self.metrics = Metrics()

    # -- public -------------------------------------------------------------

    async def chat(
        self,
        request: ChatRequest,
        key_id: int | None = None,
    ) -> ChatResponse:
        """Route and run a non-streamed completion (checks the cache first)."""
        if not request.messages:
            raise RouterError("messages must not be empty")

        self._apply_guardrails(request)

        cached = await self._try_cache_hit(request, key_id)
        if cached is not None:
            return cached

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
            self._persist(
                provider_name=model.provider,
                model_id=model.id,
                usage=usage,
                latency_ms=elapsed_ms,
                key_id=key_id,
                cached=False,
            )
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
            if spec.cache_enabled and is_cacheable(request.model_dump()):
                self._cache_put(
                    make_cache_key(request.messages),
                    serialize_cacheable(
                        model=model.id,
                        content=result.content or "",
                        finish_reason=result.finish_reason,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                    ),
                )
            if spec.redact_pii:
                self._redact_response_content(response)
            return response

        raise RouterError(f"all {attempts} candidate(s) failed: {last_error}")

    async def stream(
        self,
        request: ChatRequest,
        key_id: int | None = None,
    ) -> AsyncIterator[bytes]:
        """Route and stream SSE bytes; falls back across candidates."""
        if not request.messages:
            yield f"data: {self._no_match_message(request)}\n\n".encode()
            return
        try:
            self._apply_guardrails(request)
        except RouterBlockError as exc:
            yield f"data: [ROUTER_BLOCKED] {exc}\n\n".encode()
            return
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
                self._persist(
                    provider_name=model.provider,
                    model_id=model.id,
                    usage=Usage(),
                    latency_ms=self._ms(started),
                    key_id=key_id,
                    cached=False,
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

    def _apply_guardrails(self, request: ChatRequest) -> None:
        spec = request.router
        if spec.block_injection and messages_contain_injection(request.messages):
            raise RouterBlockError("request blocked: potential prompt-injection attempt detected")
        if spec.redact_pii:
            request.messages = redact_messages(request.messages)

    def _redact_response_content(self, response: ChatResponse) -> None:
        for choice in response.choices:
            if choice.message.content:
                choice.message.content = redact_text(choice.message.content)

    async def _try_cache_hit(self, request: ChatRequest, key_id: int | None) -> ChatResponse | None:
        """Return a cached response, or None to route normally."""
        if self.storage is None or not request.router.cache_enabled:
            return None
        if not is_cacheable(request.model_dump()):
            return None
        raw = self.storage.cache_get(make_cache_key(request.messages))
        if not raw:
            return None
        import json

        cached = json.loads(raw)
        requested = request.model or "auto"
        usage = Usage(
            prompt_tokens=int(cached.get("prompt_tokens", 0)),
            completion_tokens=int(cached.get("completion_tokens", 0)),
            total_tokens=int(cached.get("prompt_tokens", 0))
            + int(cached.get("completion_tokens", 0)),
            estimated_cost_usd=0.0,
        )
        route = RouteInfo(
            requested_model=requested,
            chosen_model=str(cached.get("model", "")),
            provider="cache",
            policy_used=request.router.policy,
            attempts=0,
            fallback_used=False,
            latency_ms=0,
            estimated_cost_usd=0.0,
            router_reason="semantic cache hit",
        )
        response = new_response(model=str(cached.get("model", "")))
        response.choices = [
            ChatChoice(
                message=ChatMessage(role="assistant", content=cached.get("content")),
                finish_reason=cached.get("finish_reason"),
            )
        ]
        response.usage = usage
        response.route = route
        self._persist(
            provider_name="cache",
            model_id=response.model,
            usage=usage,
            latency_ms=0,
            key_id=key_id,
            cached=True,
        )
        return response

    def _cache_put(self, cache_key: str, payload: dict[str, object]) -> None:
        if self.storage is None:
            return
        self.storage.cache_put(cache_key, payload)

    def _persist(
        self,
        *,
        provider_name: str,
        model_id: str,
        usage: Usage,
        latency_ms: int,
        key_id: int | None,
        cached: bool,
    ) -> None:
        """Persist a latency sample + usage record when storage is enabled."""
        if self.storage is None:
            return
        self.storage.add_latency_sample(provider_name, model_id, latency_ms)
        self.storage.record_usage(
            provider=provider_name,
            model=model_id,
            prompt_tokens=int(usage.prompt_tokens),
            completion_tokens=int(usage.completion_tokens),
            cost_usd=float(usage.estimated_cost_usd or 0.0),
            latency_ms=latency_ms,
            cached=cached,
            key_id=key_id,
        )

    def _resolve_candidates(self, request: ChatRequest) -> tuple[list[Model], str]:
        spec = request.router
        requested = request.model or "auto"
        measured = self.storage.measured_avg_ms() if self.storage is not None else None
        if requested in self.catalog:
            ordered = [self.catalog[requested]]
            for model in rank_candidates(self.catalog.values(), spec, measured):
                if model.id != requested:
                    ordered.append(model)
            return ordered, requested
        return rank_candidates(self.catalog.values(), spec, measured), "auto"

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
