"""OpenAI-compatible adapter: OpenAI, OpenRouter, or any custom base URL.

Serves both non-streamed and streamed completions. The request payload is
forwarded verbatim (minus the ``router`` field) so caller data gets through.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ai_model_router.catalog import PROVIDER_OPENAI, PROVIDER_OPENROUTER, Model
from ai_model_router.models import ChatRequest, Usage
from ai_model_router.providers.base import Provider, ProviderError, ProviderResult

OPENAI_API = "https://api.openai.com/v1"


class OpenAICompatProvider(Provider):
    """Provider backed by ``OPENAI_BASE_URL`` or ``OPENROUTER_BASE_URL``."""

    name = PROVIDER_OPENAI

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.name = PROVIDER_OPENAI
        if not key:
            or_key = os.getenv("OPENROUTER_API_KEY", "")
            or_base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
            if or_key:
                key, base_url, self.name = or_key, or_base, PROVIDER_OPENROUTER
            else:
                raise ValueError("neither OPENAI_API_KEY nor OPENROUTER_API_KEY is set")
        self._base_url = ((base_url or os.getenv("OPENAI_BASE_URL")) or OPENAI_API).rstrip("/")
        super().__init__(
            client=httpx.AsyncClient(
                timeout=90.0,
                headers={"Authorization": f"Bearer {key}"},
            )
        )

    def _payload(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": "",
            "messages": request.messages,
            "stream": stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        return payload

    async def chat(self, request: ChatRequest, model: Model) -> ProviderResult:
        payload = self._payload(request, stream=False)
        payload["model"] = self._model_id(model.id)
        response = await self._client.post(f"{self._base_url}/chat/completions", json=payload)
        if response.status_code >= 400:
            raise ProviderError(f"{self.name} {response.status_code}: {response.text[:200]}")
        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage_data = data.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        return ProviderResult(
            content=message.get("content") or "",
            finish_reason=choice.get("finish_reason"),
            usage=usage,
            raw=data,
        )

    async def stream(self, request: ChatRequest, model: Model) -> AsyncIterator[bytes]:
        payload = self._payload(request, stream=True)
        payload["model"] = self._model_id(model.id)
        async with self._client.stream(
            "POST", f"{self._base_url}/chat/completions", json=payload
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode(errors="replace")[:200]
                raise ProviderError(f"{self.name} {response.status_code}: {body}")
            async for line in response.aiter_lines():
                if line and line.startswith("data:"):
                    yield (line + "\n\n").encode()

    @staticmethod
    def _model_id(catalog_id: str) -> str:
        return catalog_id.split("openrouter:", 1)[1] if "openrouter:" in catalog_id else catalog_id
