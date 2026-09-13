"""Multi-tenant API-key authentication and per-key rate limiting.

Key resolution order (first match wins):

1. ``ROUTER_API_KEY`` (admin key)   -> unrestricted, not billed
2. ``amr_live_*`` scoped keys       -> looked up in storage, rate limited, billed

Access control:

- When neither an admin key nor storage is configured the gateway is open
  (convenient zero-config local demo against the mock provider).
- When storage is configured, ``/v1/*`` requires a valid scoped key.
- When only an admin key is configured, that exact key is required.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from ai_model_router.config import Settings
from ai_model_router.storage import ApiKey, Storage, hash_key

PROTECTED_PREFIX = "/v1/"


def _token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        return ""
    return authorization[len("Bearer ") :].strip()


@dataclass
class RateLimiter:
    """Per-key sliding-window request throttling (in-memory)."""

    _windows: dict[int, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def allow(self, key_id: int, rpm: int, now: float | None = None) -> bool:
        now = now or time.monotonic()
        window = self._windows[key_id]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= max(int(rpm), 1):
            return False
        window.append(now)
        return True


def resolve_key(
    storage: Storage | None,
    settings: Settings,
    token: str,
) -> ApiKey | None:
    """Return the scoped key for ``token``, or ``None`` when invalid."""
    if storage is None or not token:
        return None
    key = storage.get_key_by_hash(hash_key(token))
    if key is None or not key.enabled:
        return None
    return key


def make_auth_middleware(storage: Storage | None, settings: Settings) -> Any:
    """Build the auth middleware bound to this app's storage + settings."""
    limiter = RateLimiter()
    admin_key = settings.api_key

    async def auth_middleware(request: Request, call_next: Any) -> Any:
        path = request.url.path
        if not path.startswith(PROTECTED_PREFIX):
            return await call_next(request)

        token = _token(request.headers.get("authorization", ""))
        scoped = resolve_key(storage, settings, token) if storage else None

        if scoped is not None:
            assert storage is not None
            if not limiter.allow(scoped.id, scoped.rpm):
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"rate limit exceeded ({scoped.rpm} req/min)"},
                )
            if storage is not None and storage.requests_today(scoped.id) >= scoped.rpd:
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"daily quota exceeded ({scoped.rpd} req/day)"},
                )
            storage.record_request(scoped.id)
            request.state.router_key = scoped
            request.state.router_key_id = scoped.id
            return await call_next(request)

        if admin_key and token == admin_key:
            request.state.router_key = None
            request.state.router_key_id = None
            return await call_next(request)

        if not admin_key and storage is None:
            request.state.router_key = None
            request.state.router_key_id = None
            return await call_next(request)

        return JSONResponse(status_code=401, content={"detail": "invalid API key"})

    return auth_middleware
