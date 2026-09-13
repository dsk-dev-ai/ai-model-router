"""Lemon Squeezy billing: webhook signature verification and tier mapping.

Events handled (upgrade/downgrade an API key's ``tier``):

- ``subscription_created`` / ``subscription_updated`` / ``order_created``
- ``payment_success``
- ``subscription_cancelled`` / ``subscription_expired``  -> back to free

Plans are matched by variant name (substring, case-insensitive):
``business``, ``pro``, ``developer``; anything else falls back to ``free``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from ai_model_router.storage import Storage

logger = logging.getLogger(__name__)

UPGRADE_EVENTS = {
    "subscription_created",
    "subscription_updated",
    "order_created",
    "payment_success",
}
DOWNGRADE_EVENTS = {"subscription_cancelled", "subscription_expired"}

_VARIANT_TIERS = (
    ("business", "business"),
    ("pro", "pro"),
    ("developer", "developer"),
)


def verify_signature(secret: str, raw_body: bytes, signature: str) -> bool:
    """Constant-time HMAC-SHA256 check of the Lemon Squeezy webhook."""
    if not secret:
        return True
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def tier_from_variant(variant_name: str) -> str:
    lowered = variant_name.lower()
    for needle, tier in _VARIANT_TIERS:
        if needle in lowered:
            return tier
    return "free"


def _custom_data(event_data: dict[str, Any] | list[Any]) -> dict[str, Any]:
    if isinstance(event_data, list):
        return {}
    raw = event_data.get("custom_data") if isinstance(event_data, dict) else None
    return raw if isinstance(raw, dict) else {}


def apply_webhook_event(
    storage: Storage,
    event_name: str,
    event_data: dict[str, Any] | list[Any],
) -> dict[str, Any]:
    """Apply a parsed webhook event; returns a summary dict."""
    tier = tier_from_variant(
        str(event_data.get("variant_name") or "free") if isinstance(event_data, dict) else "free"
    )
    custom = _custom_data(event_data)
    raw_key_id = custom.get("key_id")
    if raw_key_id is None:
        return {"handled": False, "reason": "no custom_data.key_id"}
    try:
        key_id = int(raw_key_id)
    except (TypeError, ValueError):
        return {"handled": False, "reason": f"invalid key_id '{raw_key_id}'"}
    key = storage.get_key(key_id)
    if key is None:
        return {"handled": False, "reason": f"unknown key {key_id}"}

    if event_name in UPGRADE_EVENTS:
        new_tier = tier if tier != "free" else key.tier
        storage.set_tier(key_id, new_tier)
        return {
            "handled": True,
            "key_id": key_id,
            "tier": new_tier,
            "action": "upgrade",
        }
    if event_name in DOWNGRADE_EVENTS:
        storage.set_tier(key_id, "free")
        return {
            "handled": True,
            "key_id": key_id,
            "tier": "free",
            "action": "downgrade",
        }
    return {"handled": False, "reason": f"unhandled event '{event_name}'"}


def parse_webhook(raw_body: bytes) -> tuple[str, dict[str, Any] | list[Any]]:
    payload = json.loads(raw_body)
    event = payload.get("meta", {}).get("event_name", "")
    data = payload.get("data", {})
    attributes = data.get("attributes", {}) if isinstance(data, dict) else {}
    return str(event), (attributes if isinstance(attributes, dict) else data)
