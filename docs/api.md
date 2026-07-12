# The api service

`services/api` is the frontend's entire backend: a FastAPI app assembled in
`app.py` from one router per resource. It owns CRUD, ingestion ingress,
forecast triggering, EDA, export/share, notifications, the dashboard, and the
local dev/demo endpoints. It is one of the two services allowed to touch
Postgres (the other is `worker`).

## App assembly (`app.py`)

- CORS from `CORS_ORIGINS` (comma-separated).
- A body-size middleware rejects requests whose declared `Content-Length`
  exceeds `MAX_REQUEST_BODY_BYTES` (~8 MB) **before** parsing; the per-delivery
  point cap (below) is the backstop for chunked/unlabelled bodies.
- `Unauthorized` (from the auth provider) maps to a clean 401.
- On startup (lifespan) it loads the connector-definition YAML seeds from
  `/connectors` into `connector_definitions` so the wizard has a catalog on
  first boot.

## Dependencies & tenancy (`deps.py`)

The DI module is where the security model lives:

- `current_principal` → `AuthProvider.authenticate(Authorization header)`.
  Locally that's the fixed implicit org/user; with `MULTI_TENANT=true` it
  validates dev JWTs (minted by `POST /dev/token`).
- `require_owned_connector` / `require_owned_metric` / `require_owned_run`
  resolve a path id **scoped to the principal's org**, 404 on miss. These
  `Owned*Dep` dependencies are the *single place* org-scoping is enforced —
  routes declare their need ("an owned metric") instead of re-deriving the
  tenancy lookup in their bodies. **Every new route that takes a resource id
  must use (or follow the pattern of) these deps.**
- `get_db` yields a session that commits on success / rolls back on exception.

## Endpoint reference

### Connectors & metrics

| Endpoint | Behavior |
|---|---|
| `GET /connector-definitions` | The catalog (key, name, config_schema…) that drives the schema-generated wizard |
| `POST /connectors` | Create from a definition key + config; stores an optional secret via the `SecretsProvider` and keeps only `secret_ref`; generates `webhook_token` for push connectors |
| `GET /connectors`, `GET /connectors/{id}` | List / detail (org-scoped) |
| `PATCH /connectors/{id}` | Rename, pause/resume, edit config/cadence |
| `DELETE /connectors/{id}` | Delete, revoking the stored secret |
| `GET /connectors/{id}/runs` | Poll audit history (`connector_runs`) |
| `POST /connectors/{id}/metrics`, `GET /connectors/{id}/metrics` | Metric CRUD under a connector; `key` is the stable slug ingestion resolves against (`UNIQUE (connector_id, key)`), `seasonal_period` feeds the ml request |
| `GET /metrics` | Org-wide list with sparkline/last-point summary data |
| `GET/PATCH/DELETE /metrics/{id}` | Metric detail / edit / delete |
| `GET /metrics/{id}/data` | The series for charting |

### Forecasts, EDA, export

| Endpoint | Behavior |
|---|---|
| `POST /metrics/{id}/forecast` (202) | Inserts `forecast_runs(status='pending')` — the row **is** the job; returns the run to poll |
| `GET /forecasts/{id}` | Run status + points; the frontend polls until terminal |
| `GET /metrics/{id}/forecasts` | Run history for the metric |
| `GET /forecasts/{id}/export?format=csv\|json\|xlsx` | Streams the file and records an `export_jobs` row + blob so a share link exists for every export |
| `POST /forecasts/{id}/share?format=` | Shareable expiring link (`share_token`, 7-day TTL) |
| `GET /exports/{share_token}` | Public download; the token is the capability; 410 after expiry |
| `POST /metrics/{id}/eda` / `GET /metrics/{id}/eda` | Generate (proxies the series to ml `/eda`, persists an `eda_reports` row) / fetch latest |
| `GET /metrics/{id}/anomalies` | Anomalies flagged by the worker sweep |

### Ingestion ingress (`ingestion.py`)

Both routes converge on `shared/db/ingest.upsert_points` — the same path the
worker's poller uses — and cap a single delivery at 10,000 points (413 beyond).

- `POST /webhooks/{webhook_token}` (202): push sources. No auth header — the
  token in the path is the credential, resolved against
  `connectors.webhook_token`. Unknown or paused connector → **404, not 401/403**,
  so tokens can't be probed apart from unknown paths.
- `POST /ingest` (202): the self-hosted agent, `Authorization: Bearer <token>`
  resolved against `agents.ingestion_token_hash` (sha256 — the raw token is
  never stored). An accepted ingest doubles as a heartbeat and revives a
  `stale` agent.
- `POST /agents/heartbeat`: explicit heartbeat with the same bearer scheme.

### Agents (`agents.py`)

`POST /agents` registers an agent bound to a connector and returns the
**one-time** raw ingestion token plus a pre-filled `docker-compose.agent.yml`;
only the hash persists. `GET /agents` lists health (status, last heartbeat);
`POST /agents/{id}/revoke` kills the token.

### Notifications & dashboard (`notifications.py`)

`GET /notifications[?unread_only]`, `POST /notifications/{id}/read`,
`POST /notifications/read-all`, and `GET /notifications/unread-count` — the
latter is a single COUNT kept deliberately cheap because the header bell polls
it every 30s. `GET /dashboard` returns the org-wide aggregates for the bento
grid: connectors (+error count), metrics, data points (+last 24h), completed
forecast runs, active agents, unread notifications, open anomalies.

### Dev endpoints (`dev.py`, local edition only)

- `GET /dev/sample-metric` — the offline demo source: a fixed period-12
  sinusoid + seeded noise (`shared/synthetic.py`). 404 in production edition.
- `POST /dev/token` — mints a dev JWT for exercising the `MULTI_TENANT=true`
  path locally.

### Seeds

- `python -m api.seed` (`make seed`): connector catalog + implicit org/user +
  a demo connector polling `/dev/sample-metric` + one metric
  (`sample_signups`, `seasonal_period=12`, 1-minute cadence) + ~48-point
  backfill so a real forecast is available immediately. Idempotent.
- `python -m api.seed_live` (`make seed-live`): real free-API connectors
  (CoinGecko BTC/USD hourly, Open-Meteo London temperature hourly, Frankfurter
  USD→EUR daily) with real backfilled history; no API keys needed. Idempotent.

## Patterns to follow when extending

1. **One router file per resource**, `response_model` on every route, Pydantic
   request/response schemas in `schemas.py`, ORM→schema mapping in
   `serializers.py`.
2. **Org-scope through `Owned*Dep`** — never a raw `db.get(Model, id)` on a
   tenant-owned table.
3. **Domain values via `shared/domain.py` enums**, never bare string literals.
4. **Ingest through `upsert_points`** — never write `data_points` directly; the
   outbox row must ride the same transaction.
5. **404 over 401/403** on capability-token lookups (webhook, share token) to
   prevent probing.
6. After changing the surface, regenerate the frontend types:
   `npm run gen:api` against a running api (writes `frontend/lib/api-schema.d.ts`).

Tests live in `services/api/tests/` and run against a real Postgres
(`TEST_DATABASE_URL`), migrated once and truncated between tests; they skip
automatically when the variable is unset. Any new endpoint needs a test at the
level of `test_forecast_lifecycle.py` / `test_product_surface.py`.
