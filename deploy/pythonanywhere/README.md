# Deploy on PythonAnywhere (100% free, no credit card)

PythonAnywhere free tier: no payment method, persistent filesystem, always-on
web app at `YOURUSERNAME.pythonanywhere.com`. SQLite data survives restarts.

## 1. Add to billing ("First steps")
Free tier is auto-enabled — no card anywhere.

## 2. Upload & install the app

1. Dashboard → **Consoles → Bash**.
2. Upload the wheel from your laptop (Dashboard → **Files**, or):

```bash
# on your laptop: build + copy the wheel
cd /tmp/opencode/ai-model-router
uv build
scp dist/ai_model_router_gateway-1.0.1-py3-none-any.whl \
    YOURUSERNAME@ssh.pythonanywhere.com:.
```

3. In the Bash console:

```bash
mkdir -p ai-model-router/src
# copy the repo src (or just the wheel path):
cd ~/ai-model-router
python3.13 -m venv venv
venv/bin/pip install ~/ai_model_router_gateway-1.0.1-py3-none-any.whl
```

(If ssh upload is fiddly, use the Files page to upload the `.whl` then point
`pip` at `/home/YOURUSERNAME/ai_model_router_gateway-1.0.1-py3-none-any.whl`.)

## 3. Create the web app

**Web tab → Add a new web app** → "Manual configuration" → **Python 3.13**.

## 4. WSGI configuration file

Open the generated **WSGI configuration file** and replace its contents with
`deploy/pythonanywhere/wsgi.py` (change `yourusername` to yours, and the
`path` to `/home/YOURUSERNAME/.local/lib/python3.13/site-packages` if you
installed the wheel globally instead of in a venv).

## 5. Environment variables

**Web tab → your app → Environment variables**:

```text
ROUTER_DB        /home/YOURUSERNAME/ai-model-router/router.db
ROUTER_API_KEY   amr_admin_change_me
OPENAI_API_KEY   sk-...
ANTHROPIC_API_KEY ...
GOOGLE_API_KEY   ...
OPENROUTER_API_KEY ...
```

## 6. Reload

**Web → your app → Reload**. Your gateway is live:

```
https://YOURUSERNAME.pythonanywhere.com/          # landing page
https://YOURUSERNAME.pythonanywhere.com/health    # liveness
curl -X POST https://YOURUSERNAME.pythonanywhere.com/signup   # instant free key
```

## Free-tier notes

- 100 s of CPU per day is shared across **all** Python processes (console +
  web). Good for light traffic; a heavy /docs or streaming burst can hit it.
- Idle apps boot cold on first request (a second or two).
- SSRF/callback-safe: outbound HTTPS to your model providers is allowed on free.