"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ai_model_router.models import RouterSpec


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    default_policy: str = "priority"

    @classmethod
    def from_env(cls) -> Settings:
        raw_port = _env("ROUTER_PORT", "8000")
        try:
            port = int(raw_port)
        except ValueError:
            port = 8000
        return cls(
            api_key=_env("ROUTER_API_KEY"),
            host=_env("ROUTER_HOST", "0.0.0.0"),
            port=port,
            default_policy=_env("ROUTER_DEFAULT_POLICY", "priority"),
        )

    def default_router_spec(self) -> RouterSpec:
        return RouterSpec(policy=self.default_policy)
