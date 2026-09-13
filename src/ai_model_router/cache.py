"""Semantic cache: exact & message-normalized response cache.

The router caches assistant responses keyed on a normalized digest of the
message history (roles + whitespace/lowercased text). Only requests without
tool calls are cached, and caching can be disabled per request via
``router.cache_enabled=false``. Cached responses are billed at zero tokens so
repeat traffic stops costing money.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

_CACHE_MESSAGE_LIMIT = 20


def normalize_message(msg: dict[str, Any]) -> str:
    content = msg.get("content")
    role = msg.get("role", "")
    if isinstance(content, str):
        text = " ".join(content.split()).lower()
    else:
        text = json.dumps(content, sort_keys=True)
    return f"{role}:{text}"


def make_cache_key(messages: list[dict[str, Any]]) -> str:
    """Stable digest of the (role, normalized-content) history."""
    parts = [normalize_message(m) for m in messages[:_CACHE_MESSAGE_LIMIT]]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def serialize_cacheable(
    *,
    model: str,
    content: str,
    finish_reason: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "content": content,
        "finish_reason": finish_reason,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }


def is_cacheable(request: dict[str, Any]) -> bool:
    """A request qualifies for caching when it has text and no tool calls."""
    return bool(request.get("messages")) and not request.get("tools")