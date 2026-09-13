"""Provider adapters and a small registry.

Each provider implements :class:`Provider`. HTTP providers use an ``httpx``
client for full control over streaming and error surfacing.
"""

from __future__ import annotations

from ai_model_router.providers.anthropic import AnthropicProvider
from ai_model_router.providers.base import Provider, ProviderError, ProviderResult
from ai_model_router.providers.google import GoogleProvider
from ai_model_router.providers.mock import MockProvider
from ai_model_router.providers.openai_compat import OpenAICompatProvider

__all__ = [
    "AnthropicProvider",
    "GoogleProvider",
    "MockProvider",
    "OpenAICompatProvider",
    "Provider",
    "ProviderError",
    "ProviderResult",
]


async def default_providers() -> dict[str, Provider]:
    """Providers enabled by the environment (missing keys are skipped)."""
    registry: dict[str, Provider] = {}
    for provider_cls in (
        OpenAICompatProvider,
        AnthropicProvider,
        GoogleProvider,
        MockProvider,
    ):
        try:
            provider = provider_cls()
        except ValueError:
            continue
        registry[provider.name] = provider
    return registry
