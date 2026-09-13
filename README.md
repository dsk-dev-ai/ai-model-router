# ai-model-router

**OpenAI-compatible LLM gateway**: route every request to the *best, cheapest, or
fastest* model across providers, fall back automatically when a provider fails,
and see exactly what each call costs — all through an API your existing OpenAI
clients already speak.

```sh
export OPENAI_API_KEY=sk-...          # any provider keys you have
export ROUTER_API_KEY=your-service-key
uv run ai-model-router
```

```python
# Point your existing OpenAI SDK at the router:
client = OpenAI(base_url="http://localhost:8000/v1", api_key="your-service-key")
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
  (`gpt-4o-mini` instead of `gpt-4o` for a chat reply).
- **Reliability** — when a provider returns 5xx / quota / timeout, fall
  through to the next model instead of failing the user's request.
- **Oversight** — per-request `estimated_cost_usd`, latency, and a `/v1/usage`
  endpoint show your real spend across providers.

## How routing works

Constraint filtering happens first, then ordering by policy:

1. **Filter** by required capabilities (`tools`, `vision`, `json`,
   `long-context`), allowed providers, and an optional `max_cost_usd`.
2. **Order** by policy:
   - `priority` — your explicit model order (default: catalog latency order)
   - `cheapest` — lowest list price (input + output)
   - `fastest` — lowest latency hint
3. **Try** the top candidate; on failure, move down the list until one succeeds
   (`fallback: true`, the default).

Set `"model": "auto"` for full automatic routing, or name a specific model
(`"gpt-4o"`, `"claude-sonnet-4-20250514"`, `"gemini-2.0-flash"`,
`"openrouter:deepseek/deepseek-chat"`, …) to start there and still fall back.

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
    "fallback": true
  }
}
```

## Endpoints

| Endpoint | Description |
|---|---|
| `POST /v1/chat/completions` | Routed chat. `stream: true` returns SSE. |
| `GET /v1/models` | Catalog of routable models. |
| `GET /v1/models/{id}` | Price / capabilities / latency for one model. |
| `GET /v1/usage` | In-memory spend, calls, and avg latency per provider. |
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

### Per-model constraints example

<details>
<summary>Anthropic needs a specific auth header, Gemini a URL key, and
OpenRouter is OpenAI-compatible — all handled internally.</summary>

Providers read API keys from the environment:

| Variable | Provider | Notes |
|---|---|---|
| `OPENAI_API_KEY` | openai | `OPENAI_BASE_URL` to override |
| `ANTHROPIC_API_KEY` | anthropic | `ANTHROPIC_BASE_URL` to override |
| `GOOGLE_API_KEY` | google | `GOOGLE_BASE_URL` to override |
| `OPENROUTER_API_KEY` | openrouter | any OpenAI-compatible model via OpenRouter |
| — | mock | always enabled; `ROUTER_MOCK_FAIL_MODELS` forces failures for tests |

</details>

## Install & run

```sh
uv sync --group dev
uv run pytest -q
uv run pyright  # no; we use mypy
uv run mypy -p ai_model_router
uv run ruff check src tests
uv run ai-model-router          # http://0.0.0.0:8000
```

Try it:

```sh
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer $ROUTER_API_KEY' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello"}],
       "router":{"policy":"cheapest"}}'
```

## Roadmap → monetization

The project is structured for a hosted, subscription API (free → developer →
pro → business tiers). Planned:

- Persisted usage + billing (Lemon Squeezy / Stripe), API-key management
- Real latency telemetry per provider (replaces static hints)
- Semantic cache (same question, cheaper answer)
- Tool-call validation and output guards
- Provider-native streaming with mid-stream re-route
- Guardrails: content policy, PII redaction

## License

MIT — go build something.