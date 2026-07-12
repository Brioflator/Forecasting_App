# Architecture

Self-hostable metric collection + forecasting. Connectors collect numeric time
series on a schedule (or receive them by push), a stateless ml service turns a
series into a forecast with confidence intervals and an explicit trust verdict,
and a Next.js frontend charts, explains, and exports the results.

## Services

| Service | Port | Process | Responsibility |
|---|---|---|---|
| `frontend` | 3000 | Next.js (App Router) | Every user-facing screen; talks **only** to `api` |
| `api` | 8000 | FastAPI (`services/api`) | CRUD, ingestion ingress (webhook + agent), forecast trigger, EDA, export/share, notifications, dashboard, dev endpoints |
| `worker` | — | Long-running Python process (`services/worker`) | APScheduler polling, forecast dispatch, outbox relay, event consumers, anomaly sweep, maintenance |
| `ml` | 8100 | FastAPI (`services/ml`) | Stateless forecasting + EDA. **No DB, no auth, no state** — a pure function over the request body |
| `postgres` | 5432 | Postgres 17 | Single shared database; schema owned by SQL-first Alembic migrations in `migrations/` |
| `redis` | 6379 | Redis | Event transport (Redis Streams) behind the `EventBus` seam |

Two structural rules keep the services loosely coupled despite the shared
database:

1. **Only `api` and `worker` touch Postgres.** `ml` communicates purely via its
   REST contract (`shared/models/dto.py`) — that is what makes it independently
   testable (golden files, no DB) and horizontally scalable.
2. **The frontend talks only to `api`.** It never reaches `worker`, `ml`, or
   the database, so those stay free to change behind the `api` contract.

## Repository layout

```
services/api      FastAPI routers (one file per resource), deps.py DI, seeds
services/worker   main.py wires: scheduler + dispatch loop + relay loop + consumers
services/ml       the forecasting pipeline (see docs/ml.md)
shared/           settings, DTOs (inter-service contracts), provider seam,
                  SQLAlchemy mapping layer, the one ingestion code path
agent/            standalone self-hosted push agent (own subtree, own README)
connectors/       connector definitions as YAML seed data ("connectors are data")
migrations/       Alembic runner + hand-authored SQL (0001–0009)
frontend/         Next.js App Router app
docker/           compose file + per-service Dockerfiles
tests/            cross-service tests; note tests/shared is shared's suite
```

Python is a **uv workspace** (one root lockfile; members `services/*`, `shared`;
`agent` is a standalone subtree with its own pyproject). Dependencies are
exact-locked; `statsforecast` is additionally exact-**pinned** in
`services/ml/pyproject.toml` because golden-file determinism depends on it.

## The provider seam

Everything that differs between the local edition and a future hosted edition
sits behind a `typing.Protocol` in `shared/providers/`, resolved once at
startup by `shared/factory.py` from settings (`shared/settings.py`, env-driven):

| Concern | Protocol | Local impl (built) | Production impl (doc 02, **not built**) | Selector |
|---|---|---|---|---|
| Secrets | `SecretsProvider` | `DotenvSecretsProvider` (file at `SECRET_FILE`) | Supabase Vault | `SECRETS_IMPL` |
| Events | `EventBus` | `InProcessEventBus`, `RedisEventBus` (Streams) | Kafka | `EVENT_BUS_IMPL` |
| Blobs | `BlobStore` | `LocalBlobStore` (files under `EXPORT_DIR`) | Supabase Storage | `BLOB_STORE_IMPL` |
| Auth | `AuthProvider` | `LocalAuthProvider` (fixed org/user; dev JWTs when `MULTI_TENANT=true`) | Supabase Auth | `AUTH_IMPL` |

Rules of the seam (ADR-001 in doc 01 §13):

- No service imports a concrete provider — services call `make_*()` and depend
  on the Protocol.
- Production cases exist in the factory and raise `NotImplementedError` so the
  seam shape is visible; do not implement them until doc 02 work starts.
- To add a provider: implement the Protocol, add a `case` to the factory. If a
  new provider forces a change to a *caller*, the interface is drawn in the
  wrong place — fix the interface.

Postgres is deliberately **not** behind a seam: it is the same engine, schema,
and migrations in both editions.

## The flows

### 1. Ingestion — three routes, one code path

All three ingestion routes converge on
`shared/db/ingest.upsert_points()`, so nothing downstream knows which route
delivered the data:

- **Pull** — the worker's APScheduler fires per connector cadence →
  `worker/poller.py` fetches the secret (at call time, never cached), runs the
  extractor (`worker/extractors.py`, SSRF-guarded), and ingests.
- **Push** — `POST /webhooks/{token}` on `api`; the token in the path is the
  credential, resolved against `connectors.webhook_token` (404 on miss, so
  tokens can't be probed).
- **Agent** — the self-hosted agent POSTs `/ingest` with its bearer token
  (sha256 hash stored, never the raw token); an accepted ingest doubles as a
  heartbeat.

`upsert_points` does, in **one transaction**: dedupe within the payload →
`INSERT … ON CONFLICT (metric_id, timestamp) DO UPDATE` (idempotent by
construction — retried polls and redelivered webhooks can never duplicate a
point) → one `outbox_events` row per point. Pull runs additionally write a
`connector_runs` audit row; N consecutive failures flip the connector to
`error` and raise a notification once, on the transition.

### 2. Events — outbox → bus → consumers

`worker/relay.py` polls `outbox_events WHERE published_at IS NULL … FOR UPDATE
SKIP LOCKED`, publishes each to the `EventBus`, marks it published. At-least-
once delivery; consumers must be idempotent. The one consumer today
(`worker/consumers.py`) implements **auto-forecast-on-ingest**: a
`data_point.ingested` event enqueues a forecast run for that metric, throttled
to one per `AUTO_FORECAST_MIN_INTERVAL_MINUTES` (default 15) and never while a
run is already pending/running — which is also what makes redelivery a no-op.

### 3. Forecast lifecycle — the row is the job

There is no second job mechanism (no Celery, no queue message): the
`forecast_runs` row **is** the durable job (doc 01 §5.4).

1. `api` (`POST /metrics/{id}/forecast`) or the auto-forecast consumer inserts
   `forecast_runs(status='pending')` and returns the id.
2. `worker/dispatch.py` claims pending rows `FOR UPDATE SKIP LOCKED` (correct
   with one worker locally and N replicas later), flips each to `running`,
   loads the newest `FORECAST_MAX_SERIES_POINTS` (5000) data points, and calls
   `ml POST /forecast` over HTTP (120s read timeout — a bounded fit must never
   be abandoned mid-flight only to be re-requested).
3. On success it writes `forecast_points`, persists the resolved model +
   diagnostics into `model_params`, the trust verdict into `low_confidence`
   and `backtest` (migration 0008), sets `completed`, and raises a
   `forecast_completed` notification.
4. A **structured refusal** from ml (422: too little/broken data) is terminal —
   `status='failed'` with the detail. A **transport failure** (connection
   refused, 5xx, timeout) is retried with exponential backoff; the attempt
   count and next-attempt time ride inside `model_params` so they survive
   restarts, and the run fails terminally after
   `FORECAST_DISPATCH_MAX_ATTEMPTS` (5).
5. The frontend polls `GET /forecasts/{id}` until the status is terminal.

### 4. Anomaly detection — residual threshold against the band

`worker/anomalies.py`, swept every `ANOMALY_SWEEP_INTERVAL_SECONDS` (60): for
each metric, take the newest **completed, not-low-confidence** forecast run
(a baseline-quality band says nothing about what's anomalous — alerting off it
would be a false-positive storm), join actuals to forecast points on timestamp,
and flag actuals outside `[lower, upper]`. Severity scales with distance
outside the band relative to band width. Dedupe on `(metric_id, detected_at)`
makes sweeps idempotent; one `anomaly_detected` notification per sweep per
metric.

### 5. Export and sharing

`GET /forecasts/{id}/export?format=csv|json|xlsx` streams the file **and**
records an `export_jobs` row + stores the artifact via the `BlobStore`, so a
share link always serves identical bytes. `POST /forecasts/{id}/share` returns
a signed URL wrapping `export_jobs.share_token` (7-day TTL);
`GET /exports/{share_token}` is the public download — the token is the
capability, expiry enforced against `expires_at`.

### 6. Notifications and dashboard

Workers and the api write `notifications` rows (`forecast_completed`,
`anomaly_detected`, `connector_error`, `agent_unreachable`). The frontend bell
polls the cheap `GET /notifications/unread-count`; `GET /dashboard` returns the
nine org-wide aggregates for the home bento grid.

## Database

Schema authority is the **hand-written SQL in `migrations/versions/`** (Alembic
is only the runner); `shared/db/models.py` is a hand-maintained mapping layer
that mirrors it — never autogenerate in either direction, and treat divergence
as a bug in the models. Highlights:

- `data_points` and `forecast_points` use composite natural PKs
  (`(metric_id|run_id, timestamp)`) — idempotent ingestion for free.
- `data_points`, `connector_runs`, `audit_log` are monthly range-partitioned
  (0006); the worker creates partitions ahead via `ensure_month_partitions`.
- RLS policies live in 0005; inert with the single implicit local org, real
  when `MULTI_TENANT=true` (dev JWTs via `POST /dev/token`).
- Migration 0001 creates a minimal `auth.users` shim (`IF NOT EXISTS`) so the
  same schema works locally and on Supabase.
- If a migration file is rewritten after a database recorded it as applied,
  recreate that database — Alembic will not re-run it.

Domain vocabulary (statuses, sources, model types) is single-sourced as
`StrEnum`s in `shared/domain.py`, mirroring the DB CheckConstraints.

## Design principles to preserve

- **Loose coupling via contracts**: DTOs in `shared/models/dto.py` are the
  inter-service contracts; keep them stable and additive (new response fields
  get defaults so old/new services interoperate during rollout).
- **Policy separated from execution**: thresholds and selection logic live in
  dedicated policy modules (see docs/ml.md); executors stay dumb.
- **Honesty over silence**: fallbacks are flagged (`low_confidence`,
  `confidence_reasons`, `warning`), never hidden. Preserve this in anything new.
- **Idempotency everywhere data moves**: upserts, outbox at-least-once,
  consumer throttles, anomaly dedupe. New data paths must keep this property.
- **Bounded work**: every loop has a batch size, every fit a window and search
  bound, every request body a size cap. Unbounded growth is a bug.
