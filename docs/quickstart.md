# Quickstart

A 5-minute setup that gets you a working, metered gateway against the built-in
mock provider (no third-party API keys required).

## 1. Install

```sh
git clone https://github.com/dsk-dev-ai/ai-model-router
cd ai-model-router
uv sync --group dev
```

## 2. Create a database and an API key

```sh
ai-model-router db-init --db /tmp/demo.db
ai-model-router create-key --db /tmp/demo.db --name demo
# amr_live_<64 hex>   <- note it; shown once
```

## 3. Run the gateway

```sh
ROUTER_DB=/tmp/demo.db uv run ai-model-router serve
# or without a DB:  uv run ai-model-router serve   (open, unmetered, mock only)
```

## 4. Make your first routed call

```sh
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer amr_live_..." \
  -d '{
        "model": "auto",
        "messages": [{"role": "user", "content": "Hello from the router"}],
        "router": {"policy": "cheapest"}
      }'
```

The mock provider echoes your message and every response carries a `route` block
with the chosen model, `estimated_cost_usd`, and `latency_ms`.

## 5. Watch the caching + billing work

```sh
# repeat the same curl twice — the second returns route.router_reason =
# "semantic cache hit" with estimated_cost_usd 0.0. Then:
ai-model-router usage --db /tmp/demo.db
```

## Next steps

- Add real provider keys (`OPENAI_API_KEY`, etc.) and drop `"provider": ["mock"]`.
- Secure & scale it: [deploy.md](deploy.md).
- Manage more keys/tiers: [admin.md](admin.md).
- Charge for it: [billing.md](billing.md).