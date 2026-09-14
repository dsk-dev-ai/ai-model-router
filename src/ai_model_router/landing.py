"""Eager-loaded single-file landing page served at ``/``."""

from __future__ import annotations

from ai_model_router.pricing import TIERS


def _tier_cards() -> str:
    order = ("free", "developer", "pro", "business")
    cards = []
    for key in order:
        tier = TIERS[key]
        price = int(tier["price_usd"])
        price_html = f"${price}" if price else "Free"
        features = "".join(f"<li>{f}</li>" for f in tier["features"])
        popular = ' class="card popular"' if key == "pro" else ""
        cards.append(
            f"<div{popular}><h3>{tier['name']}</h3>"
            f'<p class="price">{price_html}<span>/mo</span></p>'
            f"<ul>{features}</ul>"
            '<a class="btn" href="https://lemon-squeezy.placeholder/" '
            f'data-plan="{key}">Choose {tier["name"]}</a></div>'
        )
    return "".join(cards)


LANDING_HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ai-model-router — the OpenAI-compatible LLM gateway</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         background: #0b0f17; color: #e6e6ff; line-height: 1.6; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 0 24px; }}
  header {{ display: flex; align-items: center; gap: 12px; padding: 24px 0; }}
  header h1 {{ font-size: 20px; }}
  header .tag {{ color: #8ee6a3; font-size: 13px; margin-left: auto; }}
  .hero {{ padding: 72px 0 48px; text-align: center; }}
  .hero h2 {{ font-size: 44px; line-height: 1.15; }}
  .hero p {{ color: #a9b3d1; font-size: 19px; max-width: 640px; margin: 20px auto 32px; }}
  .cta {{ display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }}
  .btn {{ display: inline-block; padding: 13px 26px; border-radius: 10px;
          text-decoration: none; font-weight: 600; background: #5b8cff; color: #fff; }}
  .btn.ghost {{ background: transparent; border: 1px solid #3d4366; color: #e6e6ff; }}
  code {{ background: #151b2b; border: 1px solid #242b45; border-radius: 6px;
         padding: 2px 6px; font-size: 0.9em; color: #ffd479; }}
  .feature {{ padding: 48px 0; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 18px; }}
  .box {{ background: #111828; border: 1px solid #242b45; border-radius: 12px; padding: 22px; }}
  .box h4 {{ margin-bottom: 8px; }}
  .codebox {{ background: #0c1220; border: 1px solid #242b45; border-radius: 10px;
              padding: 18px; overflow-x: auto; font-size: 14px; }}
  pre {{ margin: 0; }}
  .pricing {{ padding: 48px 0; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
           gap: 18px; margin-top: 24px; }}
  .card {{ background: #111828; border: 1px solid #242b45; border-radius: 14px;
          padding: 24px; display: flex; flex-direction: column; gap: 14px; }}
  .card.popular {{ border-color: #5b8cff; }}
  .card h3 {{ font-size: 18px; }}
  .card .price {{ font-size: 30px; font-weight: 700; color: #8ee6a3; }}
  .card .price span {{ font-size: 14px; color: #a9b3d1; font-weight: 400; }}
  .card ul {{ list-style: none; font-size: 14px; color: #a9b3d1; }}
  .card li:before {{ content: "✓ "; color: #8ee6a3; }}
  footer {{ padding: 40px 0; color: #6a7190; font-size: 13px; text-align: center; }}
  @media (max-width: 640px) {{ .hero h2 {{ font-size: 32px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>ai-model-router</h1>
    <span class="tag">● v1.0.0 — production ready</span>
  </header>

  <section class="hero">
    <h2>One API. Every great model.<br>None of the price tag.</h2>
    <p>Route each request to the cheapest or fastest LLM across OpenAI,
       Anthropic, Google and OpenRouter — with automatic fallback and
       per-request cost tracking.</p>
    <div class="cta">
      <a class="btn" href="/signup">Get a free key</a>
      <a class="btn ghost" href="/docs">Read the docs</a>
    </div>
  </section>

  <section class="feature">
    <div class="grid">
      <div class="box"><h4>Cost control</h4>Use <code>gpt-4o-mini</code> instead
        of <code>gpt-4o</code> when it's enough. The semantic cache makes repeat
        questions cost $0.</div>
      <div class="box"><h4>Reliability</h4>5xx, quota or timeout from one provider?
        Requests auto-fallthrough to the next model. No failed user calls.</div>
      <div class="box"><h4>Oversight</h4>Every response returns
        <code>estimated_cost_usd</code> and latency; a persistent usage endpoint
        tracks spend per key.</div>
      <div class="box"><h4>Privacy</h4>Optional PII redaction strips emails,
        phones and card numbers before they reach any AI provider.</div>
    </div>
  </section>

  <section class="feature">
    <div class="codebox"><pre>curl https://your-host/v1/chat/completions \\
  -H "Authorization: Bearer $AMR_KEY" \\
  -d '{{"messages":[{{"role":"user","content":"Hello"}}],
        "router":{{"policy":"cheapest"}}}}'</pre></div>
  </section>

  <section class="pricing">
    <h2>Simple pricing that scales with you</h2>
    <div class="cards">{_tier_cards()}</div>
  </section>

  <footer>© 2026 dsk-dev-ai · MIT license · running on ai-model-router v1.0.0</footer>
</div>
</body>
</html>
"""
