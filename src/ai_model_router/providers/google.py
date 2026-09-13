"""Google Gemini ``generateContent`` adapter (non-streamed)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ai_model_router.catalog import PROVIDER_GOOGLE, Model
from ai_model_router.models import ChatRequest, Usage
from ai_model_router.providers.base import Provider, ProviderError, ProviderResult

GOOGLE_API = "https://generativelanguage.googleapis.com"


class GoogleProvider(Provider):
    name = PROVIDER_GOOGLE

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.getenv("GOOGLE_API_KEY", "")
        if not key:
            raise ValueError("GOOGLE_API_KEY is not set")
        super().__init__(client=httpx.AsyncClient(timeout=60.0))
        self._api_key = key
        self._base_url = os.getenv("GOOGLE_BASE_URL", GOOGLE_API).rstrip("/")

    async def chat(self, request: ChatRequest, model: Model) -> ProviderResult:
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": str(m.get("content", ""))}],
            }
            for m in request.messages
            if m.get("role") in ("user", "assistant")
        ]
        if not contents:
            contents = [{"role": "user", "parts": [{"text": ""}]}]
        payload: dict[str, Any] = {"contents": contents}
        if request.temperature is not None:
            payload["generationConfig"] = {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens or 1024,
            }
        url = f"{self._base_url}/v1beta/models/{model.id}:generateContent?key={self._api_key}"
        response = await self._client.post(url, json=payload)
        if response.status_code >= 400:
            raise ProviderError(f"google {response.status_code}: {response.text[:200]}")
        data = response.json()
        candidates = data.get("candidates", [{}])
        text = candidates[0]["content"]["parts"][0].get("text", "") if candidates else ""
        metadata = data.get("usageMetadata", {})
        prompt_tokens = metadata.get("promptTokenCount", 0)
        completion_tokens = metadata.get("candidatesTokenCount", 0)
        usage = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        return ProviderResult(
            content=text,
            finish_reason=(candidates[0].get("finishReason") or "stop"),
            usage=usage,
            raw=data,
        )
