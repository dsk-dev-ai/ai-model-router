"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ai_model_router.models import RouterSpec


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    db_path: Path | str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    default_policy: str = "priority"
    lemon_webhook_secret: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        raw_port = _env("ROUTER_PORT", "8000")
        try:
            port = int(raw_port)
        except ValueError:
            port = 8000
        db_raw = _env("ROUTER_DB", "")
        db_path: Path | str = Path(db_raw) if db_raw else ""
        return cls(
            api_key=_env("ROUTER_API_KEY"),
            db_path=db_path,
            host=_env("ROUTER_HOST", "0.0.0.0"),
            port=port,
            default_policy=_env("ROUTER_DEFAULT_POLICY", "priority"),
            lemon_webhook_secret=_env("LEMON_WEBHOOK_SECRET"),
        )

    def default_router_spec(self) -> RouterSpec:
        return RouterSpec(policy=self.default_policy)
