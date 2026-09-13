"""Billing: Lemon Squeezy webhook parsing, signature check, tier mapping."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from ai_model_router.billing import (
    apply_webhook_event,
    parse_webhook,
    tier_from_variant,
    verify_signature,
)
from ai_model_router.config import Settings
from ai_model_router.server import create_app
from ai_model_router.storage import Storage

SECRET = "ws-secret"


def _webhook_payload(
    event: str,
    key_id: int,
    variant: str = "ai-model-router-pro",
) -> dict:
    return {
        "meta": {"event_name": event},
        "data": {
            "type": "subscriptions",
            "attributes": {"variant_name": variant, "custom_data": {"key_id": str(key_id)}},
        },
    }


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _post(app, body: dict, *, signed: bool = True, secret: str = SECRET) -> object:
    raw = json.dumps(body).encode()
    headers = {}
    if signed:
        headers["x-signature"] = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return TestClient(app).post("/webhooks/lemon", content=raw, headers=headers)


def test_verify_signature() -> None:
    body = b"hello"
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(SECRET, body, sig)
    assert not verify_signature(SECRET, b"tampered", sig)
    assert verify_signature("", body, "anything")  # no secret -> accept


def test_tier_mapping() -> None:
    assert tier_from_variant("ai-model-router-business") == "business"
    assert tier_from_variant("ai-model-router-pro") == "pro"
    assert tier_from_variant("ai-model-router-developer") == "developer"
    assert tier_from_variant("random tier") == "free"
    assert tier_from_variant("PRO") == "pro"  # case-insensitive


def test_parse_webhook() -> None:
    event, data = parse_webhook(json.dumps(_webhook_payload("order_created", 7)).encode())
    assert event == "order_created"
    assert data["custom_data"]["key_id"] == "7"


def _attrs(payload: dict) -> dict:
    return payload["data"]["attributes"]


def test_upgrade_event_raises_tier() -> None:
    storage = Storage()
    _, key = storage.create_key(name="subscriber", tier="free")
    outcome = apply_webhook_event(
        storage, "subscription_created", _attrs(_webhook_payload("subscription_created", key.id))
    )
    assert outcome["handled"]
    assert outcome["tier"] == "pro"
    assert storage.get_key(key.id).tier == "pro"  # type: ignore[union-attr]


def test_downgrade_event_returns_to_free() -> None:
    storage = Storage()
    _, key = storage.create_key(name="churner", tier="business")
    outcome = apply_webhook_event(
        storage,
        "subscription_cancelled",
        _attrs(_webhook_payload("subscription_cancelled", key.id)),
    )
    assert outcome["handled"]
    assert outcome["action"] == "downgrade"
    assert storage.get_key(key.id).tier == "free"  # type: ignore[union-attr]


def test_unknown_event_ignored() -> None:
    storage = Storage()
    _, key = storage.create_key(name="n/a")
    outcome = apply_webhook_event(
        storage, "test_triggered", _attrs(_webhook_payload("test_triggered", key.id))
    )
    assert not outcome["handled"]


def test_missing_key_id_unhandled() -> None:
    storage = Storage()
    payload = {"meta": {"event_name": "order_created"}, "data": {"attributes": {}}}
    outcome = apply_webhook_event(storage, "order_created", payload["data"]["attributes"])
    assert not outcome["handled"]


def test_webhook_endpoint_upgrades_key() -> None:
    storage = Storage()
    _, key = storage.create_key(name="web")
    app = create_app(settings=Settings(lemon_webhook_secret=SECRET), storage=storage)
    resp = _post(app, _webhook_payload("order_created", key.id))
    assert resp.status_code == 200
    assert storage.get_key(key.id).tier == "pro"  # type: ignore[union-attr]


def test_webhook_rejects_bad_signature() -> None:
    storage = Storage()
    _, key = storage.create_key(name="web")
    app = create_app(settings=Settings(lemon_webhook_secret=SECRET), storage=storage)
    resp = _post(app, _webhook_payload("order_created", key.id), signed=False)
    assert resp.status_code == 401
    assert storage.get_key(key.id).tier == "free"  # type: ignore[union-attr]
