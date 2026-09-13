# Admin

## Key lifecycle

```sh
ai-model-router db-init --db /var/lib/router/router.db

ai-model-router create-key --db /var/lib/router/router.db \
  --name "partner-api" --tier developer --rpm 60
# amr_live_<hex>  <- shown once

ai-model-router list-keys --db /var/lib/router/router.db
# id    status  tier       prefix      name
# 1     enabled developer  amr_live_d2f9...   partner-api

ai-model-router revoke-key --db /var/lib/router/router.db 1
```

## Tiers

Default quotas enforced automatically (override per key with `--rpm`/`--rpd`):

| Tier       | req/min | req/day |
|------------|---------|---------|
| free       | 30      | 500     |
| developer  | 60      | 5,000   |
| pro        | 300     | 50,000  |
| business   | 1,000   | 500,000 |

## API status

```sh
ai-model-router usage --db router.db
# calls:          1234
# cost (USD):     1.234
# prompt tokens:  145321
# completion tok: 23412
# cache hits:     58
```

Admin status is also available over the network (behind `/v1/` auth):

```
GET /v1/admin/health
```