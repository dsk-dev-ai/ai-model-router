# Billing (Lemon Squeezy)

The gateway upgrades API keys when a subscription/order arrives and downgrades
them back to `free` on cancellation/expiry.

## Lemon Squeezy setup

1. Create a product with variants named to include one of:
   `business`, `pro`, or `developer`. (Any other name maps to `free`.)
2. In the checkout, pass the customer's API key id as custom data:

   ```json
   "custom_data": {"key_id": "3"}
   ```

3. In **Settings → Webhooks**, add `https://your-host/webhooks/lemon` and
   copy the signing secret.

## Router configuration

```sh
LEMON_WEBHOOK_SECRET=whsec_... uv run ai-model-router serve
```

## Behavior

| Event | Effect |
|---|---|
| `subscription_created` / `subscription_updated` / `order_created` / `payment_success` | set key tier from variant name |
| `subscription_cancelled` / `subscription_expired` | downgrade key to `free` |
| anything else / no `custom_data.key_id` | ignored (422) |

Signatures are verified with HMAC-SHA256 (`x-signature` header) when a secret is
configured; invalid signatures return 401 and change nothing.

## Client flow

1. Developer signs up, gets a `free` key from the app.
2. Purchases a plan → Lemon Squeezy sends the webhook → tier lifts to `pro`.
3. Rate limits relax automatically (`300` rpm / `50_000` rpd) and usage keeps
   accumulating in `/v1/usage` for invoices.