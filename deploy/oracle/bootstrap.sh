#!/usr/bin/env bash
# One-time / upgrade bootstrap for the Oracle Always Free VM.
# Idempotent: safe to re-run to pull a newer image and restart.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

VERSION="${ROUTER_IMAGE_VERSION:-1.0.1}"
IMAGE="ghcr.io/dsk-dev-ai/ai-model-router:${VERSION}"
DATA_DIR=/srv/router/data
ENV_FILE=/etc/ai-model-router.env
SERVICE=/etc/systemd/system/ai-model-router.service

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo bash bootstrap.sh" >&2
  exit 1
fi

echo "==> installing docker"
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq docker.io
  systemctl enable --now docker
fi

echo "==> opening ports 80/443"
iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT || true
iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT || true
netfilter-persistent save >/dev/null 2>&1 || true

mkdir -p "$DATA_DIR"

if [ ! -f "$ENV_FILE" ]; then
  if [ -f ./router.env ]; then
    install -m 600 ./router.env "$ENV_FILE"
    echo "==> applied ./router.env -> $ENV_FILE"
  else
    touch "$ENV_FILE"
    echo "==> WARNING: no secrets yet ($ENV_FILE empty); set them and rerun"
  fi
fi

echo "==> pulling $IMAGE"
docker pull "$IMAGE"

echo "==> installing systemd unit"
cat > "$SERVICE" <<EOF
[Unit]
Description=AI Model Router gateway
After=docker.service
Requires=docker.service

[Service]
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/docker rm -f ai-model-router
ExecStart=/usr/bin/docker run --name ai-model-router \\
  --restart unless-stopped \\
  -p 80:8000 \\
  --env-file $ENV_FILE \\
  -e ROUTER_DB=/data/router.db \\
  -e ROUTER_HOST=0.0.0.0 \\
  -e ROUTER_PORT=8000 \\
  --mount type=bind,source=$DATA_DIR,target=/data \\
  $IMAGE
ExecStop=/usr/bin/docker stop ai-model-router

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ai-model-router
systemctl restart ai-model-router

echo "==> waiting for health"
for _ in $(seq 1 30); do
  if curl -fsS localhost/health >/dev/null 2>&1; then
    echo "==> LIVE: http://<ip>/health  http://<ip>/signup"
    exit 0
  fi
  sleep 2
done
echo "==> not healthy yet (endpoint needs OPENAI_API_KEY etc.); retry bootstrap or check:" >&2
echo "    sudo journalctl -u ai-model-router" >&2
exit 1