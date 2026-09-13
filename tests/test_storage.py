"""SQLite storage tests: keys, usage, latency, and cache."""

from ai_model_router.storage import Storage, generate_key, hash_key


def test_generate_key_format() -> None:
    key = generate_key()
    assert key.startswith("amr_live_")
    assert len(key) == len("amr_live_") + 40
    assert hash_key(key) != hash_key(generate_key())


def test_create_and_lookup_key() -> None:
    storage = Storage()
    plaintext, record = storage.create_key(name="test")
    assert plaintext.startswith("amr_live_")
    assert record.tier == "free"
    assert storage.get_key_by_hash(hash_key(plaintext)) is not None
    assert storage.get_key_by_hash("deadbeef") is None


def test_key_prefix_does_not_leak_secret() -> None:
    storage = Storage()
    plaintext, record = storage.create_key(name="no-leak")
    assert record.prefix not in plaintext[len("amr_live_") :]


def test_list_and_revoke() -> None:
    storage = Storage()
    storage.create_key(name="a")
    _, key_b = storage.create_key(name="b")
    assert len(storage.list_keys()) == 2
    assert storage.revoke_key(key_b.id) is True
    assert storage.get_key(key_b.id).enabled is False  # type: ignore[union-attr]


def test_tier_defaults_and_upgrade() -> None:
    storage = Storage()
    _, key = storage.create_key(name="tier-test")
    assert key.rpm == 30 and key.rpd == 500
    assert storage.set_tier(key.id, "pro") is True
    upgraded = storage.get_key(key.id)
    assert upgraded is not None
    assert upgraded.tier == "pro" and upgraded.rpm == 300


def test_usage_record_and_summary() -> None:
    storage = Storage()
    _, key = storage.create_key(name="u")
    storage.record_usage(
        provider="mock",
        model="mock/echo",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
        latency_ms=12,
        key_id=key.id,
    )
    storage.record_usage(provider="mock", model="mock/echo", cached=True, key_id=key.id)
    summary = storage.usage_summary()
    assert summary["calls"] == 2
    assert abs(summary["cost"] - 0.001) < 1e-9
    assert storage.usage_today(key.id) == 2


def test_latency_telemetry_aggregates() -> None:
    storage = Storage()
    storage.add_latency_sample("mock", "mock/echo", 100)
    storage.add_latency_sample("mock", "mock/echo", 200)
    stats = storage.latency_stats()
    assert stats["mock/mock/echo"]["avg_ms"] == 150.0
    assert storage.measured_latency("mock/echo") == 150.0
    assert storage.measured_latency("unknown") is None


def test_cached_roundtrip() -> None:
    storage = Storage()
    payload = {"key": "v", "tokens": 1}
    assert storage.cache_get("abc") is None
    storage.cache_put("abc", payload)
    assert storage.cache_get("abc") == '{"key": "v", "tokens": 1}'
