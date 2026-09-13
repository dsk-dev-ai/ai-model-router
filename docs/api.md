# API Reference

Base URL: `https://<your-host>/v1` — the surface is OpenAI-shaped, so the
OpenAI Python/JS SDKs work by swapping `base_url`.

Authentication: `Authorization: Bearer <amr_live_...>` (or the admin key).

## `POST /chat/completions`

Request (everything optional except `messages`):

```jsonc
{
  "model": "auto",                          // or any catalog id
  "messages": [{"role": "user", "content": "Hi"}],
  "stream": false,                          // true -> SSE
  "temperature": 0.7,
  "max_tokens": 256,
  "tools": [...],                           // tool-calling when supported
  "router": {
    "policy": "priority",                   // priority | cheapest | fastest
    "providers": [],
    "requires": [],                         // vision | tools | json | long-context
    "max_cost_usd": null,
    "priority": [],
    "fallback": true,
    "cache_enabled": true,
    "redact_pii": false,
    "block_injection": false
  }
}
```

Response: standard chat completion object plus:

```jsonc
"usage": { "...": 0, "estimated_cost_usd": 0.00018 },
"route": {
  "requested_model": "auto",
  "chosen_model": "gpt-4o-mini",
  "provider": "openai",
  "policy_used": "cheapest",
  "attempts": 1,
  "fallback_used": false,
  "latency_ms": 431,
  "estimated_cost_usd": 0.00018,
  "router_reason": "first-choice model"
}
```

Errors: `400` (no matching model / guardrail block), `401` (bad key),
`429` (rate or daily quota), `502` (all candidates failed).

## `GET /models`

Catalog of routable models: `{"object":"list","data":[{"id","owned_by"}]}`.

## `GET /models/{id}`

Prices, capabilities, latency hint for one model (`404` if unknown).

## `GET /usage`

Persisted totals: calls, cost, tokens, cache hits, plus per-model avg latency.

```jsonc
{
  "total_calls": 1234,
  "total_cost_usd": 1.234,
  "providers": { "mock": {"calls": 1234, "cost_usd": 0.0, "latency_avg_ms": 4} },
  "persisted": {"calls": 1234, "cost_usd": 1.234,
                "prompt_tokens": 1000, "completion_tokens": 500,
                "cache_hits": 58},
  "latency_avg_ms": { "mock/echo": 4.2 }
}
```

## `GET /admin/health`

Auth-protected provider + storage status.

## `POST /webhooks/lemon`

Lemon Squeezy billing webhook (not under `/v1`; HMAC-verified when
`LEMON_WEBHOOK_SECRET` is set). Doc: [billing.md](billing.md).

## `GET /health`

Public liveness. `GET /docs` serves OpenAPI UI.