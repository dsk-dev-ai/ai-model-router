"""FastAPI application.

Endpoints (all OpenAI-shaped so existing SDK clients work by swapping the
base URL to this service):

- ``POST /v1/chat/completions``   routed chat; supports ``stream: true``
- ``GET  /v1/models``             catalog overview
- ``GET  /v1/models/{id}``        single model details
- ``GET  /v1/usage``              in-memory spend / latency snapshot
- ``GET  /health``                liveness
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ai_model_router.config import Settings
from ai_model_router.models import ChatRequest, ChatResponse
from ai_model_router.providers.anthropic import AnthropicProvider
from ai_model_router.providers.base import Provider
from ai_model_router.providers.google import GoogleProvider
from ai_model_router.providers.mock import MockProvider
from ai_model_router.providers.openai_compat import OpenAICompatProvider
from ai_model_router.router import RouterEngine, RouterError, RouterNoMatchError

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


def create_app(
    engine: RouterEngine | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.engine = engine or RouterEngine(providers=build_providers())
        yield

    app = FastAPI(
        title="ai-model-router",
        description=(
            "OpenAI-compatible LLM gateway: route to best/cheapest/fastest model, "
            "automatic fallback on failure, and per-request cost + latency tracking."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine or RouterEngine(providers=build_providers())

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next: Any) -> JSONResponse | Any:
        path = request.url.path
        if path.startswith("/v1/") and settings.api_key:
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {settings.api_key}":
                return JSONResponse(status_code=401, content={"detail": "invalid API key"})
        return await call_next(request)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "ai-model-router"}

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": "ai-model-router",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "endpoints": [
                "/v1/chat/completions",
                "/v1/models",
                "/v1/usage",
                "/health",
            ],
        }

    @app.post(
        "/v1/chat/completions",
        response_model=ChatResponse,
    )
    async def chat_completions(payload: ChatRequest) -> ChatResponse | StreamingResponse:
        engine: RouterEngine = app.state.engine
        try:
            if payload.stream:
                return StreamingResponse(
                    engine.stream(payload),
                    media_type="text/event-stream",
                )
            return await engine.chat(payload)
        except RouterNoMatchError as exc:
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

    @app.get("/v1/usage")
    async def usage() -> dict[str, Any]:
        engine: RouterEngine = app.state.engine
        snapshot = engine.metrics.snapshot()
        total_cost = round(sum(float(s["cost_usd"]) for s in snapshot.values()), 6)
        total_calls = sum(int(s["calls"]) for s in snapshot.values())
        return {
            "total_calls": total_calls,
            "total_cost_usd": total_cost,
            "providers": snapshot,
        }

    return app
