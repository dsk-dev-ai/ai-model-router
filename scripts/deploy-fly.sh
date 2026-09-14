#!/usr/bin/env bash
# Deploy ai-model-router to Fly.io.
#
# Prereqs:
#   1. curl -L https://fly.io/install.sh | sh        (the `fly` CLI)
#   2. fly auth login
#   3. fly launch (first time only, to create the app + volume) — see below
#
# Usage:  bash scripts/deploy-fly.sh
set -euo pipefail

APP="${FLY_APP:-ai-model-router}"
SECRETS=()

echo "==> Fly.io deploy: $APP"

# Required secrets (set all you have; skipped if unset so the app still boots):
assign() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then
    echo "==> secret $name (from env)"
    SECRETS+=("$name=${!name}")
  else
    echo "==> SKIP secret $name (unset)"
  fi
}
assign ROUTER_API_KEY
assign OPENAI_API_KEY
assign ANTHROPIC_API_KEY
assign GOOGLE_API_KEY
assign OPENROUTER_API_KEY
assign LEMON_WEBHOOK_SECRET

if [[ ${#SECRETS[@]} -gt 0 ]]; then
  fly secrets set "${SECRETS[@]}" --app "$APP"
fi

fly deploy --app "$APP"

echo "==> Done. Health check:"
curl -s "https://$APP.fly.dev/health" && echo
echo "==> Landing: https://$APP.fly.dev/"
echo "==> Instant key: curl -X POST https://$APP.fly.dev/signup"