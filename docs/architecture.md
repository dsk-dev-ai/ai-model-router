# ai-model-router — documentation

## Components

```
        OpenAI SDK / curl / any client
                     │  POST /v1/chat/completions
                     ▼
        ┌──────────────────────┐   API auth (ROUTER_API_KEY)
        │  FastAPI app          │
        │  server.py            │
        └──────────┬───────────┘
                   ▼
        ┌──────────────────────┐
        │  RouterEngine         │  router.py
        │  policy.py            │  1. filter by capabilities/providers/cost
        │                       │  2. order by policy (priority/cheapest/fastest)
        │                       │  3. try candidate, fall back on ProviderError
        └──────────┬───────────┘
                   ▼
        ┌──────────────────────┐   catalog.py  (prices, latency hints, caps)
        │  Providers            │
        │  openai / openrouter  │   OpenAI-compatible passthrough (+stream)
        │  anthropic / google   │   native message formats
        │  mock (offline)       │   deterministic; ROUTER_MOCK_FAIL_MODELS
        └──────────┬───────────┘
                   ▼
        ┌──────────────────────┐   metrics.py (in-memory)
        │  usage + output       │   response.route{...} block, /v1/usage
        └──────────────────────┘
```

## Request lifecycle (non-streamed)

1. `RouterEngine.chat` validates `messages`.
2. `_resolve_candidates` builds the ordered candidate list (explicit model first,
   then policy-ranked fallbacks; `model == "auto"` skips to full policy ranking).
3. For each candidate: the matching provider is looked up. Missing provider is
   recorded and skipped. Provider errors are recorded, and (unless
   `fallback: false`) the engine moves to the next candidate.
4. On success the response is priced from catalog list prices and the `route`
   block is attached; metrics are updated.

## Cost model

- `Model` entries carry `price_in` / `price_out` per 1M tokens (USD).
- `estimated_cost_usd = prompt_tokens / 1e6 * price_in + completion_tokens / 1e6 * price_out`.
- These are list-price estimates; **provider invoices are authoritative**. Use
  the router for budgeting and anomaly alerting, never for billing reconciliation.

## Streaming

`stream: true` returns SSE passthrough via the OpenAI-compatible provider.
Fallback happens at connection time: if the first candidate fails before
producing a chunk, the next candidate takes over. Anthropic / Google adapters
do not stream yet (they raise and trigger fallback to a streaming-capable
provider). Mid-stream failures terminate the stream (cannot re-route an
already-started response).

## Adding a model

Add an entry to `MODEL_CATALOG` in `catalog.py`:

```python
Model(
    id="provider/model-name",
    provider="openai",            # must match a registered Provider name
    price_in=0.15, price_out=0.60, # per 1M tokens, USD
    ctx=128_000,
    latency_hint=2,                # 1 (fast) .. 5 (slow)
    capabilities=frozenset({"tools", "json"}),
)
```

Custom models on any OpenAI-compatible endpoint work via `OPENROUTER_API_KEY` /
`OPENROUTER_BASE_URL` (or `OPENAI_BASE_URL` for a self-hosted endpoint).

## Running locally

```sh
uv sync --group dev
uv run ai-model-router
```

Example call:

```sh
curl -s localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"ping"}],
       "router":{"policy":"cheapest"}}'
```

Because no provider keys are set, traffic is served by the built-in mock
provider — everything else (policy, fallback, cost, usage) works exactly as in
production.