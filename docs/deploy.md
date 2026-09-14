# Deployment

The gateway is a stateless FastAPI app plus a SQLite database. Persist the DB
file on durable disk; keep everything else ephemeral.

Shared setup on every platform:

- `ROUTER_API_KEY` — admin key (unmetered). Random string, keep secret.
- `ROUTER_DB` — path to the SQLite file on persistent storage.
- Provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...) — optional.
- `LEMON_WEBHOOK_SECRET` — optional, only if you use [billing](billing.md).

## Fly.io

`fly.toml` is included and wires a 1 GB persistent volume at `/data`. The
one-liner helper is `scripts/deploy-fly.sh` (set provider keys as env vars, it
injects them as Fly secrets).

First time only (creates the app + volume):

```sh
curl -L https://fly.io/install.sh | sh
fly auth login
fly launch --name ai-model-router --no-deploy
fly volumes create data --region fra --size 1
```

Then each release:

```sh
export ROUTER_API_KEY=... OPENAI_API_KEY=...   # etc.
bash scripts/deploy-fly.sh
```

Alternatively, set secrets by hand:

```sh
fly secrets set ROUTER_API_KEY=... ROUTER_DB=/data/router.db OPENAI_API_KEY=...
fly deploy
```

## Render

Create a **Docker**-runtime service from this repo using `render.yaml` (blueprint
includes the 1 GB disk and health check):

- Render → Blueprints → New Blueprint → select this repo.

## Docker (anywhere)

```sh
docker run -d --name ai-model-router \
  -p 8000:8000 \
  -e ROUTER_API_KEY=... \
  -e ROUTER_DB=/data/router.db \
  -v router-data:/data \
  ghcr.io/dsk-dev-ai/ai-model-router:1.0.0
```

The image runs as a non-root user and has a `/health` HEALTHCHECK.

## Operational notes

- Scale out by pointing replicas at the same volume (or move to Postgres; see
  roadmap). SQLite handles one writer — one instance is the default topology.
- `/v1/usage` and `/health` are your monitoring hooks; access logs are emitted
  as `method= path= status= duration_ms=` lines.
- Blocked/quota responses (`429`) are safe to retry; `400` guardrail blocks are
  client bugs, not outages.