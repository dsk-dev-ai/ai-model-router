# ai-model-router

**OpenAI-compatible LLM gateway**: route every request to the *best, cheapest, or
fastest* model across providers, fall back automatically when a provider fails,
and see exactly what each call costs — all through an API your existing OpenAI
clients already speak.

v1.0.0 adds the production layer: **multi-tenant API keys, per-key rate limits,
persisted usage/billing, a semantic cache, guardrails, and an admin CLI** — so it
can run as a hosted subscription product, not just a local tool.

```sh
uv run ai-model-router db-init --db /var/lib/router/router.db
uv run ai-model-router create-key --db /var/lib/router/router.db --name my-app
# amr_live_<64 hex>  ->  keep this; it is shown once
ROUTER_DB=/var/lib/router/router.db \
ROUTER_API_KEY=admin-secret \
uv run ai-model-router serve
```

```python
# Point your existing OpenAI SDK at the router:
client = OpenAI(base_url="http://localhost:8000/v1", api_key="amr_live_...")
reply   = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Say hi"}],
    extra_body={"router": {"policy": "cheapest", "fallback": True}},
)
```

## Why

Companies spend far too much on LLMs because one model gets glued to one call
path. A router fixes three things at once:

- **Cost** — pick the cheapest model that can actually do the job
  (`gpt-4o-mini` instead of `gpt-4o` for a chat reply); repeat questions hit a
  **semantic cache** and cost zero.
- **Reliability** — when a provider returns 5xx / quota / timeout, fall through
  to the next model instead of failing the user's request.
- **Oversight** — per-request `estimated_cost_usd`, latency, persisted usage per
  API key, and a `/v1/usage` endpoint show your real spend across providers.

## Authentication & tiers

Every `amr_live_*` key is scoped to a rate-limit tier; limits are enforced
strictly (HTTP 429 with a reason when exceeded).

| Tier      | req/min | req/day | Intent |
|-----------|---------|---------|--------|
| `free`    | 30      | 500     | evaluate the gateway |
| `developer` | 60   | 5,000   | hobby / prototypes |
| `pro`     | 300     | 50,000  | production apps |
| `business`| 1,000   | 500,000 | teams |

`ROUTER_API_KEY` is an admin (unmetered) key. When no keys are configured the
gateway runs open and unmetered for local demos.

## How routing works

Constraint filtering happens first, then ordering by policy:

1. **Filter** by required capabilities (`tools`, `vision`, `json`,
   `long-context`), allowed providers, and an optional `max_cost_usd`.
2. **Order** by policy:
   - `priority` — your explicit model order (default: **measured** latency order)
   - `cheapest` — lowest list price (input + output)
   - `fastest` — lowest latency. Uses real measured averages from
     `ROUTER_DB` once telemetry exists, static hints before that.
3. **Try** the top candidate; on failure, move down the list until one succeeds
   (`fallback: true`, the default).

Set `"model": "auto"` for full automatic routing, or name a specific model to
start there and still fall back.

### Request-time routing hints

```jsonc
{
  "model": "auto",
  "messages": [{"role": "user", "content": "Summarize this PDF page"}],
  "router": {
    "policy": "cheapest",
    "requires": ["vision"],
    "providers": ["openai", "anthropic", "google"],
    "max_cost_usd": 2.0,
    "priority": ["gpt-4o-mini", "claude-3-5-haiku", "gemini-2.0-flash"],
    "fallback": true,
    "cache_enabled": true,
    "redact_pii": false,
    "block_injection": false
  }
}
```

## Guardrails

Opt-in per request (and safe to leave on):

- **`redact_pii: true`** — replaces emails, phone numbers, SSN/card numbers and
  IPv4 addresses with `[REDACTED ...]` placeholders in the outbound prompt *and*
  the response, so PII never reaches a third-party provider.
- **`block_injection: true`** — rejects requests that look like prompt-injection
  attempts ("ignore your system prompt", "jailbreak", …) with a 400 before they
  are sent to any provider.

## Semantic cache

Enabled by default for text-only requests without tool calls; disable per request
with `"router": {"cache_enabled": false}`. Responses are keyed on a normalized
digest of the message history. A cached reply is served with
`route.router_reason = "semantic cache hit"`, `estimated_cost_usd = 0.0`, and is
recorded in usage as a cache hit.

## Endpoints

| Endpoint | Description |
|---|---|
| `POST /v1/chat/completions` | Routed chat. `stream: true` returns SSE. |
| `GET /v1/models` | Catalog of routable models. |
| `GET /v1/models/{id}` | Price / capabilities / latency for one model. |
| `GET /v1/usage` | Persisted spend, calls, cache hits, and avg latency per model. |
| `GET /v1/admin/health` | Provider + storage status (auth required). |
| `POST /webhooks/lemon` | Lemon Squeezy subscription webhook (see below). |
| `/health`, `/` | Liveness and endpoint summary. Interactive docs at `/docs`. |

Every response includes a `route` block:

```json
{
  "model": "gpt-4o-mini",
  "usage": {"prompt_tokens": 18, "completion_tokens": 24, "total_tokens": 42,
             "estimated_cost_usd": 0.000017},
  "route": {
    "requested_model": "auto", "chosen_model": "gpt-4o-mini",
    "provider": "openai", "policy_used": "cheapest",
    "attempts": 2, "fallback_used": true,
    "latency_ms": 431, "estimated_cost_usd": 0.000017,
    "router_reason": "served by openai after 1 failure(s)"
  }
}
```

## Admin CLI

```sh
ai-model-router db-init --db router.db        # create schema
ai-model-router create-key --db router.db --name api --tier pro
ai-model-router list-keys --db router.db      # prefix + tier only
ai-model-router revoke-key --db router.db 3
ai-model-router usage --db router.db
```

## Billing (Lemon Squeezy)

Create product variants whose names contain `developer`, `pro`, or `business`,
and pass the API key id through `custom_data.key_id` at checkout. Point the store
webhook at `POST /webhooks/lemon` and set `LEMON_WEBHOOK_SECRET`. Purchases
upgrade the key's tier; cancellation/expiry downgrade it to `free`.

## Providers

| Variable | Provider | Notes |
|---|---|---|
| `OPENAI_API_KEY` | openai | `OPENAI_BASE_URL` to override |
| `ANTHROPIC_API_KEY` | anthropic | `ANTHROPIC_BASE_URL` to override |
| `GOOGLE_API_KEY` | google | `GOOGLE_BASE_URL` to override |
| `OPENROUTER_API_KEY` | openrouter | any OpenAI-compatible model via OpenRouter |
| — | mock | always enabled; `ROUTER_MOCK_FAIL_MODELS` forces failures for tests |

## Deploy

The repo ships `Dockerfile` (non-root + healthcheck), `fly.toml`
(Fly.io + persistent disk), and `render.yaml` (Render blueprint). Deploy docs:
[docs/deploy.md](docs/deploy.md). Container images are published to
`ghcr.io/dsk-dev-ai/ai-model-router` and the Python package to PyPI on tagged
releases.

## Docs

- [docs/quickstart.md](docs/quickstart.md) — 5-minute setup guide
- [docs/deploy.md](docs/deploy.md) — Fly.io / Render / Docker deployments
- [docs/admin.md](docs/admin.md) — key management & usage
- [docs/billing.md](docs/billing.md) — Lemon Squeezy integration
- [docs/architecture.md](docs/architecture.md) — design notes
- [docs/api.md](docs/api.md) — API reference

## Install & run

```sh
uv sync --group dev
uv run pytest -q
uv run mypy -p ai_model_router
uv run ruff check src tests
uv run ai-model-router serve
```

Try it:

```sh
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer amr_live_...' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello"}],
       "router":{"policy":"cheapest"}}'
```

## Roadmap

- Provider-native streaming for Anthropic/Gemini (OpenAI-format SSE already works)
- Tool-call validation / output verifiers
- Prometheus-format metrics export
- Postgres backend option for the storage layer

## License

MIT — go build something.