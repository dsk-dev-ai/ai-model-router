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

from ai_model_router.auth import make_auth_middleware
from ai_model_router.config import Settings
from ai_model_router.models import ChatRequest, ChatResponse
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


def create_app(
    engine: RouterEngine | None = None,
    settings: Settings | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    external_storage = storage is not None
    storage = storage or (Storage(settings.db_path) if settings.db_path else None)

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
        version="0.1.0",
        lifespan=lifespan,
    )
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
