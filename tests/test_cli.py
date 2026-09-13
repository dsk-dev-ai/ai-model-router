"""Admin CLI end-to-end against a temp SQLite file."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ai_model_router.__main__ import main
from ai_model_router.config import Settings
from ai_model_router.server import create_app
from ai_model_router.storage import Storage


def _run(*argv: str) -> None:
    main(list(argv))


def test_db_init_then_create_list_revoke_usage(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = str(tmp_path / "router.db")
    _run("db-init", "--db", db)
    _run("create-key", "--db", db, "--name", "demo", "--tier", "pro")
    keys = Storage(db).list_keys()
    assert len(keys) == 1
    assert keys[0].tier == "pro"
    key_id = keys[0].id
    _run("revoke-key", "--db", db, str(key_id))
    assert Storage(db).get_key(key_id).enabled is False  # type: ignore[union-attr]
    _run("usage", "--db", db)


def test_create_key_rpm_override(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = str(tmp_path / "router.db")
    _run("db-init", "--db", db)
    _run("create-key", "--db", db, "--name", "custom", "--rpm", "5")
    key = Storage(db).list_keys()[0]
    assert key.rpm == 5


def test_admin_health_shows_providers_and_storage() -> None:
    storage = Storage()
    plaintext, _ = storage.create_key(name="ops")
    app = create_app(settings=Settings(), storage=storage)
    with TestClient(app) as c:
        headers = {"Authorization": f"Bearer {plaintext}"}
        resp = c.get("/v1/admin/health", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["providers"]["mock"] == "configured"
        assert body["storage"] == "sqlite"


def test_admin_health_requires_auth_when_admin_key_set() -> None:
    app = create_app(settings=Settings(api_key="admin-1"))
    with TestClient(app) as c:
        assert c.get("/v1/admin/health").status_code == 401
        assert (
            c.get(
                "/v1/admin/health", headers={"Authorization": "Bearer admin-1"}
            ).status_code
            == 200
        )