"""Public pricing tiers and signup metadata.

Mirrors the tier defaults enforced in storage/auth so the landing page and the
runtime agree on what each plan costs and allows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TIERS: dict[str, dict[str, Any]] = {
    "free": {
        "name": "Free",
        "price_usd": 0,
        "rpm": 30,
        "rpd": 500,
        "features": [
            "Routing across all providers",
            "30 requests/min, 500/day",
            "Semantic cache",
            "Community support",
        ],
    },
    "developer": {
        "name": "Developer",
        "price_usd": 19,
        "rpm": 60,
        "rpd": 5_000,
        "features": [
            "Everything in Free",
            "5,000 requests/day",
            "PII redaction + guardrails",
            "Usage analytics",
        ],
    },
    "pro": {
        "name": "Pro",
        "price_usd": 79,
        "rpm": 300,
        "rpd": 50_000,
        "features": [
            "Everything in Developer",
            "50,000 requests/day",
            "Priority support",
            "SLA: 99.9% uptime",
        ],
    },
    "business": {
        "name": "Business",
        "price_usd": 299,
        "rpm": 1_000,
        "rpd": 500_000,
        "features": [
            "Everything in Pro",
            "500,000 requests/day",
            "Dedicated infrastructure",
            "Named support engineer",
        ],
    },
}


def tiers_json(key: str = "tiers") -> dict[str, object]:
    return {key: TIERS}


@dataclass
class SignupResult:
    key_id: int
    api_key: str
    tier: str
    rpm: int
    rpd: int

    def to_dict(self) -> dict[str, object]:
        return {
            "key_id": self.key_id,
            "api_key": self.api_key,
            "tier": self.tier,
            "rpm": self.rpm,
            "rpd": self.rpd,
            "base_url": "{base}/v1",
        }
