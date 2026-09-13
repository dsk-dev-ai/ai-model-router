"""Deterministic offline provider for development and tests.

Always enabled so the router works with zero API keys. Fails deterministically
when ``ROUTER_MOCK_FAIL_MODELS`` (comma-separated model ids) is set, which lets
tests exercise fallback without network access.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from ai_model_router.catalog import PROVIDER_MOCK, Model
from ai_model_router.models import ChatRequest, Usage
from ai_model_router.providers.base import Provider, ProviderError, ProviderResult


class MockProvider(Provider):
    name = PROVIDER_MOCK

    def __init__(self, fail_models: str | None = None) -> None:
        super().__init__()
        raw = fail_models if fail_models is not None else os.getenv("ROUTER_MOCK_FAIL_MODELS", "")
        self._fail_models = {m.strip() for m in raw.split(",") if m.strip()}

    def _assert_ok(self, model: Model) -> None:
        if model.id in self._fail_models:
            raise ProviderError(f"mock provider failed for {model.id}")

    async def chat(self, request: ChatRequest, model: Model) -> ProviderResult:
        self._assert_ok(model)
        input_text = "\n".join(
            str(m.get("content", "")) if isinstance(m, dict) else str(m) for m in request.messages
        )
        prompt_tokens = max(1, len(input_text) // 4)
        return ProviderResult(
            content=f"[mock:{self.name}] echo: {input_text[:120] or '(empty)'}",
            finish_reason="stop",
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=prompt_tokens,
                total_tokens=prompt_tokens * 2,
            ),
            raw={"mock": True},
        )

    async def stream(self, request: ChatRequest, model: Model) -> AsyncIterator[bytes]:
        self._assert_ok(model)
        content = f"[mock:{self.name}] echo: streamed"
        for i in range(0, len(content) + 1, 8):
            chunk = (
                'data: {"id":"cmpl-mock","object":"chat.completion.chunk",'
                '"choices":[{"index":0,"delta":{"content":"' + content[i : i + 8] + '"}}]}\n\n'
            )
            yield chunk.encode()
        yield b"data: [DONE]\n\n"
