# Deploy to Oracle Cloud Always Free (turnkey)

Runs the official container on a free-for-ever Oracle VM. No code changes,
persistent SQLite on the VM disk, restarts automatically.

## 1. One-time: create the VM (Oracle console, ~10 min)

1. Sign up at https://signup.oraclecloud.com — **free**, card asked once to
   verify your identity (a hold may appear, it is NOT charged). Choose "Always
   Free" resources when picking shapes.
2. Create a VM instance:
   - Image: **Ubuntu 22.04** (shows an "Always Free" banner)
   - Shape: **VM.Standard.E2.1.Micro** (AMD, 1 GB RAM) — pick the free one
   - Upload your SSH public key, save the private key.
3. Open port 80 + 443 in the VCN security list:
   - VCN → your VCN → Security Lists → Default → Add Ingress Rules
   - Source `0.0.0.0/0`, TCP 80 and 443 (and 22 for SSH if you want external SSH).

Copy the instance's public IP.

## 2. Configure secrets

Put your provider keys in a file on your laptop (it gets copied to the VM):

```bash
cat > ~/router.env <<'EOF'
ROUTER_API_KEY=amr_admin_change_me
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
EOF
chmod 600 ~/router.env
```

## 3. Deploy

```bash
IP=YOUR_VM_PUBLIC_IP
scp ~/router.env ubuntu@$IP:router.env
scp -r deploy/oracle ubuntu@$IP:oracle    # run from repo root
ssh ubuntu@$IP "bash oracle/bootstrap.sh"
curl http://$IP/health        # -> {"status":"ok",...}
curl -X POST http://$IP/signup  # -> instant free key
```

`bootstrap.sh` is idempotent: installs Docker, pulls the image, installs a
systemd unit that survives reboots, and applies secrets on every start.

## Images

Pulls `ghcr.io/dsk-dev-ai/ai-model-router:<VERSION>` (default `latest` tag =
latest release). To upgrade:

```bash
ssh ubuntu@$IP "bash oracle/bootstrap.sh"   # re-pulls + restarts
```

## Firewall notes

Oracle's default Ubuntu image opens ports via `iptables-persistent`. The script
opens 80/443 itself, so the security-list ingress rules (step 1) are the only
cloud-side config you need.