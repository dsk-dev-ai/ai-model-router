"""Provider interface shared by all adapters."""

from __future__ import annotations

from abc import ABC
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from ai_model_router.catalog import Model
from ai_model_router.models import ChatRequest, Usage


class ProviderError(RuntimeError):
    """Raised when a provider call fails; drives router fallback."""


@dataclass
class ProviderResult:
    content: str
    finish_reason: str | None
    usage: Usage
    role: str = "assistant"
    raw: dict[str, Any] | None = None


class Provider(ABC):
    name: str

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(self, request: ChatRequest, model: Model) -> ProviderResult:
        """Run one non-streamed completion."""
        raise NotImplementedError

    async def stream(self, request: ChatRequest, model: Model) -> AsyncIterator[bytes]:
        """Stream SSE bytes to the caller (passthrough)."""
        raise ProviderError(f"provider '{self.name}' does not support streaming yet")
        yield b""  # unreachable; keeps this an async generator
