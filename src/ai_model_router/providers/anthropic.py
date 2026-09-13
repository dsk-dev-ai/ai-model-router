"""Anthropic ``/v1/messages`` adapter (non-streamed)."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ai_model_router.catalog import PROVIDER_ANTHROPIC, Model
from ai_model_router.models import ChatRequest, Usage
from ai_model_router.providers.base import Provider, ProviderError, ProviderResult

ANTHROPIC_API = "https://api.anthropic.com"


class AnthropicProvider(Provider):
    name = PROVIDER_ANTHROPIC

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        super().__init__(
            client=httpx.AsyncClient(
                timeout=60.0,
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
        )
        self._base_url = os.getenv("ANTHROPIC_BASE_URL", ANTHROPIC_API).rstrip("/")

    async def chat(self, request: ChatRequest, model: Model) -> ProviderResult:
        payload: dict[str, Any] = {
            "model": model.id,
            "max_tokens": request.max_tokens or 1024,
            "messages": [
                {
                    "role": m["role"],
                    "content": m.get("content", ""),
                }
                for m in request.messages
                if m.get("role") in ("user", "assistant")
            ],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        response = await self._client.post(f"{self._base_url}/v1/messages", json=payload)
        if response.status_code >= 400:
            raise ProviderError(f"anthropic {response.status_code}: {response.text[:200]}")
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage_data = {
            "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
            "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
        }
        total = usage_data["prompt_tokens"] + usage_data["completion_tokens"]
        usage = Usage(**usage_data, total_tokens=total)
        return ProviderResult(
            content=text,
            finish_reason=data.get("stop_reason"),
            usage=usage,
            raw=data,
        )
