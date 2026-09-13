"""Persistent storage: API keys, usage, latency telemetry, and semantic cache.

Backed by SQLite (stdlib only) so the router runs anywhere with zero extra
dependencies. ``ROUTER_DB`` sets the file path; default is in-memory.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    prefix     TEXT NOT NULL,
    key_hash   TEXT NOT NULL UNIQUE,
    tier       TEXT NOT NULL DEFAULT 'free',
    rpm        INTEGER NOT NULL DEFAULT 60,
    rpd        INTEGER NOT NULL DEFAULT 1000,
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                TEXT NOT NULL,
    key_id            INTEGER,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL NOT NULL DEFAULT 0,
    latency_ms        INTEGER NOT NULL DEFAULT 0,
    cached            INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS usage_key_ts ON usage (key_id, ts);
CREATE TABLE IF NOT EXISTS requests (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts   TEXT NOT NULL,
    key_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS requests_key_ts ON requests (key_id, ts);
CREATE TABLE IF NOT EXISTS latency (
    provider TEXT NOT NULL,
    model    TEXT NOT NULL,
    calls    INTEGER NOT NULL DEFAULT 0,
    total_ms INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, model)
);
CREATE TABLE IF NOT EXISTS cache (
    key      TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    ts       TEXT NOT NULL
);
"""

KEY_PREFIX = "amr_live_"


def hash_key(key: str) -> str:
    """One-way hash used for storage; the plaintext key is never persisted."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_key() -> str:
    """Return a new scoped API key (``amr_live_<40 hex>``)."""
    import secrets

    return f"{KEY_PREFIX}{secrets.token_hex(20)}"


@dataclass
class ApiKey:
    id: int
    name: str
    prefix: str
    tier: str
    rpm: int
    rpd: int
    enabled: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prefix": self.prefix,
            "tier": self.tier,
            "rpm": self.rpm,
            "rpd": self.rpd,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }


class Storage:
    """Thread-safe SQLite wrapper."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        path: str | Path = db_path or ":memory:"
        init_schema = path == ":memory:" or not Path(path).exists()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        if init_schema:
            self._executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _executescript(self, script: str) -> None:
        with self._lock:
            self._conn.executescript(script)

    # -- API keys -----------------------------------------------------------

    def create_key(
        self,
        *,
        name: str,
        tier: str = "free",
        rpm: int | None = None,
        rpd: int | None = None,
    ) -> tuple[str, ApiKey]:
        """Persist a new key and return ``(plaintext, record)`` once only."""
        plain = generate_key()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._conn.execute(
                "INSERT INTO api_keys (name, prefix, key_hash, tier, rpm, rpd, enabled, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    name,
                    plain[: len(KEY_PREFIX) + 8],
                    hash_key(plain),
                    tier,
                    rpm or self._default(tier)[0],
                    rpd or self._default(tier)[1],
                    now,
                ),
            )
            self._conn.commit()
        return plain, cast(ApiKey, self.get_key_by_hash(hash_key(plain)))

    def _default(self, tier: str) -> tuple[int, int]:
        table = {
            "free": (30, 500),
            "developer": (60, 5_000),
            "pro": (300, 50_000),
            "business": (1_000, 500_000),
        }
        return table.get(tier, table["free"])

    def get_key_by_hash(self, key_hash: str) -> ApiKey | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
            ).fetchone()
        return self._row_to_key(row)

    def get_key(self, key_id: int) -> ApiKey | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
        return self._row_to_key(row)

    def list_keys(self) -> list[ApiKey]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM api_keys ORDER BY id").fetchall()
        result: list[ApiKey] = []
        for row in rows:
            key = self._row_to_key(row)
            if key is not None:
                result.append(key)
        return result

    def revoke_key(self, key_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("UPDATE api_keys SET enabled = 0 WHERE id = ?", (key_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def set_tier(self, key_id: int, tier: str) -> bool:
        rpm, rpd = self._default(tier)
        with self._lock:
            cur = self._conn.execute(
                "UPDATE api_keys SET tier = ?, rpm = ?, rpd = ? WHERE id = ?",
                (tier, rpm, rpd, key_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row_to_key(row: sqlite3.Row | None) -> ApiKey | None:
        if row is None:
            return None
        return ApiKey(
            id=row["id"],
            name=row["name"],
            prefix=row["prefix"],
            tier=row["tier"],
            rpm=row["rpm"],
            rpd=row["rpd"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )

    # -- usage --------------------------------------------------------------

    def record_usage(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        cached: bool = False,
        key_id: int | None = None,
    ) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (ts, key_id, provider, model, prompt_tokens,"
                " completion_tokens, cost_usd, latency_ms, cached)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now,
                    key_id,
                    provider,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    latency_ms,
                    1 if cached else 0,
                ),
            )
            self._conn.commit()

    def usage_today(self, key_id: int) -> int:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM usage WHERE key_id = ? AND ts LIKE ?",
                (key_id, f"{day}%"),
            ).fetchone()
        return int(row["n"])

    def record_request(self, key_id: int) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._conn.execute("INSERT INTO requests (ts, key_id) VALUES (?, ?)", (now, key_id))
            self._conn.commit()

    def requests_today(self, key_id: int) -> int:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM requests WHERE key_id = ? AND ts LIKE ?",
                (key_id, f"{day}%"),
            ).fetchone()
        return int(row["n"])

    def usage_summary(self, since_ts: str | None = None) -> dict[str, Any]:
        clause = "WHERE ts >= ?" if since_ts else ""
        params: tuple[Any, ...] = (since_ts,) if since_ts else ()
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS calls,"
                " COALESCE(SUM(cost_usd), 0) AS cost,"
                " COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,"
                " COALESCE(SUM(completion_tokens), 0) AS completion_tokens,"
                f" COALESCE(SUM(CASE WHEN cached = 1 THEN 1 ELSE 0 END), 0) AS cached"
                f" FROM usage {clause}",
                params,
            ).fetchone()
        return dict(row)

    # -- latency telemetry --------------------------------------------------

    def add_latency_sample(self, provider: str, model: str, latency_ms: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO latency (provider, model, calls, total_ms)"
                " VALUES (?, ?, 1, ?)"
                " ON CONFLICT(provider, model) DO UPDATE SET"
                " calls = calls + 1, total_ms = total_ms + excluded.total_ms",
                (provider, model, latency_ms),
            )
            self._conn.commit()

    def latency_stats(self) -> dict[str, dict[str, float]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT provider, model, calls, total_ms FROM latency"
            ).fetchall()
        return {
            f"{r['provider']}/{r['model']}": {
                "calls": r["calls"],
                "avg_ms": round(r["total_ms"] / r["calls"], 1),
            }
            for r in rows
        }

    def measured_latency(self, model: str) -> float | None:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM latency WHERE model = ?", (model,)).fetchall()
        if not rows:
            return None
        total_ms = sum(r["total_ms"] for r in rows)
        calls = sum(r["calls"] for r in rows)
        return total_ms / calls if calls else None

    # -- semantic cache -----------------------------------------------------

    def cache_get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT response FROM cache WHERE key = ?", (key,)).fetchone()
        return row["response"] if row else None

    def cache_put(self, key: str, response: dict[str, Any]) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, response, ts) VALUES (?, ?, ?)",
                (key, json.dumps(response), now),
            )
            self._conn.commit()
