"""FastAPI application.

Endpoints (all OpenAI-shaped so existing SDK clients work by swapping the
base URL to this service):

- ``POST /v1/chat/completions``    routed chat; supports ``stream: true``
- ``GET  /v1/models``              catalog overview
- ``GET  /v1/models/{id}``         single model details
- ``GET  /v1/usage``               persisted spend / latency snapshot
- ``POST /webhooks/lemon``         Lemon Squeezy billing webhook
- ``GET  /health``                 liveness
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ai_model_router.auth import RateLimiter, make_auth_middleware
from ai_model_router.billing import apply_webhook_event, parse_webhook, verify_signature
from ai_model_router.config import Settings
from ai_model_router.landing import LANDING_HTML
from ai_model_router.models import ChatRequest, ChatResponse
from ai_model_router.pricing import SignupResult, tiers_json
from ai_model_router.providers.anthropic import AnthropicProvider
from ai_model_router.providers.base import Provider
from ai_model_router.providers.google import GoogleProvider
from ai_model_router.providers.mock import MockProvider
from ai_model_router.providers.openai_compat import OpenAICompatProvider
from ai_model_router.router import (
    RouterBlockError,
    RouterEngine,
    RouterError,
    RouterNoMatchError,
)
from ai_model_router.storage import Storage

PROVIDER_CLASSES = (
    OpenAICompatProvider,
    AnthropicProvider,
    GoogleProvider,
    MockProvider,
)


def build_providers() -> dict[str, Provider]:
    """Instantiate every provider with a valid API key; skip the rest."""
    providers: dict[str, Provider] = {}
    for cls in PROVIDER_CLASSES:
        try:
            provider = cls()
        except ValueError:
            continue
        providers[provider.name] = provider
    return providers


request_logger = logging.getLogger("ai_model_router.access")

SIGNUP_RPM = 1


def create_app(
    engine: RouterEngine | None = None,
    settings: Settings | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    external_storage = storage is not None
    storage = storage or (Storage(settings.db_path) if settings.db_path else None)
    signup_limiter = RateLimiter()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.storage = storage
        app.state.engine = engine or RouterEngine(providers=build_providers(), storage=storage)
        yield
        if storage is not None and not external_storage:
            storage.close()

    app = FastAPI(
        title="ai-model-router",
        description=(
            "OpenAI-compatible LLM gateway: route to best/cheapest/fastest model, "
            "automatic fallback on failure, and per-request cost + latency tracking."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next: Any) -> Any:
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        request_logger.info(
            "method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            getattr(response, "status_code", "?"),
            elapsed_ms,
        )
        return response

    app.state.settings = settings
    app.state.storage = storage
    app.state.engine = engine or RouterEngine(providers=build_providers(), storage=storage)

    auth_handler = make_auth_middleware(storage, settings)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next: Any) -> JSONResponse | Any:
        return await auth_handler(request, call_next)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "ai-model-router"}

    @app.get("/", include_in_schema=False)
    async def landing() -> HTMLResponse:
        return HTMLResponse(LANDING_HTML)

    @app.get("/api", include_in_schema=False)
    async def api_summary() -> dict[str, object]:
        return {
            "service": "ai-model-router",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "endpoints": [
                "/v1/chat/completions",
                "/v1/models",
                "/v1/usage",
                "/v1/admin/health",
                "/signup",
                "/pricing",
                "/webhooks/lemon",
                "/health",
            ],
        }

    @app.get("/pricing", include_in_schema=False)
    async def pricing() -> dict[str, object]:
        return tiers_json()

    @app.post("/signup", include_in_schema=False, response_model=None)
    async def signup(request: Request) -> JSONResponse:
        if storage is None:
            return JSONResponse(status_code=422, content={"detail": "storage not configured"})
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )
        if not signup_limiter.allow(client_ip, SIGNUP_RPM):
            return JSONResponse(
                status_code=429,
                content={"detail": "slow down — one free key per minute"},
            )
        plaintext, record = storage.create_key(name=f"signup:{client_ip}")
        return JSONResponse(
            status_code=200,
            content=SignupResult(
                key_id=record.id,
                api_key=plaintext,
                tier=record.tier,
                rpm=record.rpm,
                rpd=record.rpd,
            ).to_dict(),
        )

    @app.post(
        "/v1/chat/completions",
        response_model=ChatResponse,
    )
    async def chat_completions(
        payload: ChatRequest, request: Request
    ) -> ChatResponse | StreamingResponse:
        engine: RouterEngine = app.state.engine
        key_id: int | None = getattr(request.state, "router_key_id", None)
        try:
            if payload.stream:
                return StreamingResponse(
                    engine.stream(payload, key_id=key_id),
                    media_type="text/event-stream",
                )
            return await engine.chat(payload, key_id=key_id)
        except RouterNoMatchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RouterBlockError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RouterError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/models")
    async def models() -> dict[str, object]:
        engine: RouterEngine = app.state.engine
        return {
            "object": "list",
            "data": [
                {"id": mid, "owned_by": m.provider} for mid, m in sorted(engine.catalog.items())
            ],
        }

    @app.get("/v1/models/{model_id:path}")
    async def model_detail(model_id: str) -> dict[str, object]:
        engine: RouterEngine = app.state.engine
        model = engine.catalog.get(model_id)
        if model is None:
            raise HTTPException(status_code=404, detail=f"unknown model '{model_id}'")
        return model.to_dict()

    @app.get("/v1/admin/health")
    async def admin_health() -> dict[str, Any]:
        engine: RouterEngine = app.state.engine
        return {
            "status": "ok",
            "providers": {name: "configured" for name in sorted(engine.providers)},
            "storage": "sqlite" if storage is not None else "none",
            "keys_enabled": storage is not None and bool(storage.list_keys()),
        }

    @app.get("/v1/usage")
    async def usage() -> dict[str, Any]:
        engine: RouterEngine = app.state.engine
        snapshot = engine.metrics.snapshot()
        total_cost = round(sum(float(s["cost_usd"]) for s in snapshot.values()), 6)
        total_calls = sum(int(s["calls"]) for s in snapshot.values())
        result: dict[str, Any] = {
            "total_calls": total_calls,
            "total_cost_usd": total_cost,
            "providers": snapshot,
        }
        if storage is not None:
            summary = storage.usage_summary()
            result["persisted"] = {
                "calls": summary["calls"],
                "cost_usd": round(summary["cost"], 6),
                "prompt_tokens": summary["prompt_tokens"],
                "completion_tokens": summary["completion_tokens"],
                "cache_hits": summary["cached"],
            }
            result["latency_avg_ms"] = storage.latency_stats()
        return result

    @app.post("/webhooks/lemon")
    async def lemon_squeezy_webhook(request: Request) -> JSONResponse:
        if storage is None:
            return JSONResponse(
                status_code=422,
                content={"handled": False, "reason": "storage not configured"},
            )
        raw = await request.body()
        signature = request.headers.get("x-signature", "")
        if not verify_signature(settings.lemon_webhook_secret, raw, signature):
            return JSONResponse(
                status_code=401,
                content={"handled": False, "reason": "invalid signature"},
            )
        event_name, event_data = parse_webhook(raw)
        outcome = apply_webhook_event(storage, event_name, event_data)
        status = 200 if outcome["handled"] else 422
        return JSONResponse(status_code=status, content=outcome)

    return app
