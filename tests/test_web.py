"""Public marketing endpoints: signup key minting, pricing, landing page."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai_model_router.config import Settings
from ai_model_router.server import SIGNUP_RPM, create_app
from ai_model_router.storage import Storage


def _app() -> TestClient:
    return TestClient(create_app(settings=Settings(), storage=Storage()))


def test_landing_page_served() -> None:
    with _app() as c:
        resp = c.get("/")
        assert resp.status_code == 200
        assert "Get a free key" in resp.text
        assert "One API" in resp.text


def test_pricing_lists_all_tiers() -> None:
    with _app() as c:
        resp = c.get("/pricing")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["tiers"]) == {"free", "developer", "pro", "business"}
        assert body["tiers"]["free"]["price_usd"] == 0


def test_signup_returns_one_time_key() -> None:
    with _app() as c:
        resp = c.post("/signup", headers={"X-Forwarded-For": "203.0.113.9"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["api_key"].startswith("amr_live_")
        assert body["tier"] == "free"
        assert body["rpm"] == 30


def test_signup_rate_limited_per_ip() -> None:
    with _app() as c:
        assert c.post("/signup", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 200
        assert c.post("/signup", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 429
        assert c.post("/signup", headers={"X-Forwarded-For": "198.51.100.4"}).status_code == 200


def test_signup_disabled_without_storage() -> None:
    with TestClient(create_app(settings=Settings())) as c:
        assert c.post("/signup").status_code == 422


def test_signed_up_key_works() -> None:
    with _app() as c:
        key = c.post("/signup", headers={"X-Forwarded-For": "203.0.113.9"}).json()["api_key"]
        headers = {"Authorization": f"Bearer {key}"}
        chat = c.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "router": {"priority": ["mock/echo"]},
            },
            headers=headers,
        )
        assert chat.status_code == 200
        assert chat.json()["model"] == "mock/echo"


def test_signup_rpm_constant_sane() -> None:
    assert SIGNUP_RPM >= 1
    assert SIGNUP_RPM <= 5
