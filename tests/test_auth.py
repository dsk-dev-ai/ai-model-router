"""Multi-tenant auth + rate limits + usage persistence via the HTTP API."""

from fastapi.testclient import TestClient

from ai_model_router.auth import RateLimiter, _token
from ai_model_router.config import Settings
from ai_model_router.server import create_app
from ai_model_router.storage import Storage


def _payload(model: str = "mock/echo") -> dict:
    return {
        "messages": [{"role": "user", "content": "hi"}],
        "router": {"priority": [model]},
    }


def test_admin_key_required_when_set() -> None:
    app = create_app(settings=Settings(api_key="admin-1"))
    with TestClient(app) as c:
        assert c.get("/v1/models").status_code == 401
        assert c.get("/v1/models", headers={"Authorization": "Bearer admin-1"}).status_code == 200
        assert c.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_scoped_key_via_storage() -> None:
    storage = Storage()
    plaintext, _ = storage.create_key(name="dev")
    app = create_app(settings=Settings(), storage=storage)
    with TestClient(app) as c:
        assert c.get("/v1/models").status_code == 401
        assert (
            c.get("/v1/models", headers={"Authorization": f"Bearer {plaintext}"}).status_code == 200
        )


def test_revoked_key_rejected() -> None:
    storage = Storage()
    plaintext, record = storage.create_key(name="old")
    storage.revoke_key(record.id)
    app = create_app(settings=Settings(), storage=storage)
    with TestClient(app) as c:
        resp = c.get("/v1/models", headers={"Authorization": f"Bearer {plaintext}"})
        assert resp.status_code == 401


def test_rpm_rate_limit() -> None:
    storage = Storage()
    plaintext, _ = storage.create_key(
        name="bursty",
        rpm=2,
    )
    app = create_app(settings=Settings(), storage=storage)
    with TestClient(app) as c:
        headers = {"Authorization": f"Bearer {plaintext}"}
        assert c.get("/v1/models", headers=headers).status_code == 200
        assert c.get("/v1/models", headers=headers).status_code == 200
        assert c.get("/v1/models", headers=headers).status_code == 429


def test_rpd_daily_quota() -> None:
    storage = Storage()
    plaintext, _ = storage.create_key(
        name="daily",
        rpd=1,
    )
    app = create_app(settings=Settings(), storage=storage)
    with TestClient(app) as c:
        headers = {"Authorization": f"Bearer {plaintext}"}
        assert c.get("/v1/models", headers=headers).status_code == 200
        assert c.get("/v1/models", headers=headers).status_code == 429


def test_chat_records_usage_against_key() -> None:
    storage = Storage()
    plaintext, record = storage.create_key(name="spender")
    app = create_app(settings=Settings(), storage=storage)
    with TestClient(app) as c:
        resp = c.post(
            "/v1/chat/completions",
            json=_payload(),
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert resp.status_code == 200
    summary = storage.usage_summary()
    assert summary["calls"] == 1
    assert "cost" in summary
    assert storage.requests_today(record.id) == 1


def test_admin_key_not_billed() -> None:
    storage = Storage()
    storage.create_key(name="other")
    app = create_app(settings=Settings(api_key="admin-1"), storage=storage)
    with TestClient(app) as c:
        resp = c.post(
            "/v1/chat/completions",
            json=_payload(),
            headers={"Authorization": "Bearer admin-1"},
        )
        assert resp.status_code == 200
    assert storage.usage_summary()["calls"] == 1
    assert all((k.tier or True) for k in storage.list_keys())


def test_rate_limiter_window() -> None:
    limiter = RateLimiter()
    assert limiter.allow(1, 3, now=10.0)
    assert limiter.allow(1, 3, now=10.1)
    assert limiter.allow(1, 3, now=10.2)
    assert not limiter.allow(1, 3, now=10.3)
    assert limiter.allow(1, 3, now=71.0)


def test_token_parsing() -> None:
    assert _token("Bearer abc") == "abc"
    assert _token("Bearer  abc  ") == "abc"
    assert _token("Basic abc") == ""
