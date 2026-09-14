"""HTTP API integration tests via FastAPI TestClient (mock provider only)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_model_router.config import Settings
from ai_model_router.server import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app(settings=Settings(api_key=""))
    with TestClient(app) as c:
        return c


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "model": "auto",
        "messages": [{"role": "user", "content": "hello router"}],
    }
    body.update(overrides)
    return body


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_serves_landing_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "ai-model-router" in response.text
    assert "Simple pricing" in response.text


def test_api_summary_lists_endpoints(client: TestClient) -> None:
    response = client.get("/api")
    assert response.status_code == 200
    assert "/v1/chat/completions" in response.json()["endpoints"]


def test_chat_completions_routes_to_mock(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json=_payload(router={"policy": "priority", "priority": ["mock/echo"]}),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "mock/echo"
    assert data["route"]["attempts"] == 1
    assert data["route"]["fallback_used"] is False
    assert data["usage"]["total_tokens"] > 0
    assert data["choices"][0]["message"]["role"] == "assistant"


def test_chat_respects_cheapest_policy(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json=_payload(router={"policy": "cheapest"}),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["route"]["policy_used"] == "cheapest"
    assert data["route"]["chosen_model"] == "mock/echo"


def test_no_match_returns_400(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json=_payload(router={"policy": "cheapest", "providers": ["nonexistent"]}),
    )
    assert response.status_code == 400
    assert "no model satisfies" in response.json()["detail"]


def test_empty_messages_returns_error(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [], "router": {"policy": "priority"}},
    )
    assert response.status_code == 502
    assert "messages" in response.json()["detail"]


def test_streaming_completion(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json=_payload(stream=True, router={"priority": ["mock/echo"]}),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert b"data: [DONE]" in response.content


def test_models_list(client: TestClient) -> None:
    response = client.get("/v1/models")
    assert response.status_code == 200
    ids = [m["id"] for m in response.json()["data"]]
    assert "gpt-4o" in ids
    assert "mock/echo" in ids


def test_model_detail(client: TestClient) -> None:
    response = client.get("/v1/models/mock/echo")
    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_model_detail_missing_returns_404(client: TestClient) -> None:
    response = client.get("/v1/models/nope")
    assert response.status_code == 404


def test_usage_tracks_calls_and_cost(client: TestClient) -> None:
    client.post(
        "/v1/chat/completions",
        json=_payload(router={"priority": ["mock/echo"]}),
    )
    response = client.get("/v1/usage")
    assert response.status_code == 200
    data = response.json()
    assert data["total_calls"] >= 1
    assert "mock" in data["providers"]


def test_api_key_enforced_when_configured() -> None:
    app = create_app(settings=Settings(api_key="secret-123"))
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/v1/models").status_code == 401
        assert (
            c.get("/v1/models", headers={"Authorization": "Bearer secret-123"}).status_code == 200
        )
        assert (
            c.post(
                "/v1/chat/completions",
                json=_payload(router={"priority": ["mock/echo"]}),
            ).status_code
            == 401
        )
