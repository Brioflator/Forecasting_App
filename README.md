# Forecast Platform

Self-hostable metric collection + forecasting: configure a connector, collect
data on a schedule, get a SARIMA/ETS forecast with confidence intervals, export
it. Local, open-source edition — no cloud account required.

Reference docs: [`forecast-platform-project-guide.md`](forecast-platform-project-guide.md)
(the master spec), build guides `01`–`05` (local build, deploy, ml service,
frontend, implementation plan).

## Quickstart

Requires Docker + Docker Compose and ~2 GB RAM.

```bash
git clone <repo> && cd forecast-platform
cp .env.example .env          # local-safe defaults already filled in
cp frontend/.env.example frontend/.env
make up                       # pg, redis, api, worker, ml, frontend
make seed                     # demo connector + metric + 48-point backfill
# open http://localhost:3000 → Connectors → Sample signups → Forecast → Export CSV
```

The seeded demo is fully offline: the `api` ships a local-only
`GET /dev/sample-metric` endpoint emitting a fixed period-12 sinusoid; the
seeded connector polls it every minute, and the 48-point backfill means a real
SARIMA forecast is available immediately — no waiting for data to accumulate.

## Services

| Service | Port | What it does |
|---|---|---|
| `frontend` | 3000 | Next.js app — connector list, metric detail (chart + export) |
| `api` | 8000 | FastAPI — connector/metric CRUD, forecast trigger, CSV export |
| `worker` | — | APScheduler poller, forecast dispatch (`forecast_runs` queue), outbox relay |
| `ml` | 8100 | Stateless forecasting core — `/forecast`, `/eda`; no DB, no auth |
| `postgres` | 5432 | Single shared Postgres (schema in `/migrations`, SQL-first) |
| `redis` | 6379 | Event transport (Redis Streams) behind the `EventBus` seam |

Everything cloud-swappable sits behind a provider interface in
`shared/providers/` selected by `APP_EDITION` (+ per-concern overrides) in
`shared/factory.py` — see doc 1 §2. The production implementations
(Supabase Vault/Storage/Auth, Kafka) are doc 2 scope and raise
`NotImplementedError` until then.

## Development

```bash
uv sync --all-packages        # one lockfile, four workspace members
make test                     # ruff + mypy + pytest (DB tests need the compose pg)
make regen-golden             # rewrite ml golden fixtures — review the diff!
```

Test layout (plan 05 §2.6): `ml` tests are pure in-process (golden files,
ladder coverage, contract tests — no DB); `api`/`worker` tests run against the
compose Postgres's `forecast_test` database, migrated once and truncated
between tests. Skipped automatically when `TEST_DATABASE_URL` is unset.

## Repository layout

```
services/api      FastAPI: CRUD, forecast trigger, export, /dev/sample-metric, seed
services/worker   scheduler + poller + forecast dispatch + outbox relay
services/ml       forecasting ladder + EDA (stateless; the product core)
shared/           settings, DTOs, provider seam, SQLAlchemy mapping layer
migrations/       Alembic runner + hand-authored SQL (0001–0004; 0005/0006 are
                  intentionally empty placeholders for RLS + partitioning, MVP scope)
connectors/       connector definition seeds (YAML) — "connectors are data"
frontend/         Next.js App Router app
docker/           compose file + per-service Dockerfiles
```

## Status

Local product complete — MVP scope (guide §9) plus the product layer,
everything short of production deployment (doc 2: Supabase + always-on host +
Vercel, which is the next phase):

- **Ingestion, three ways** — pull (scheduled poller with retry/backoff), push
  (`POST /webhooks/{token}`, e.g. Braze Currents), and the self-hosted
  [agent](agent/README.md) (`POST /ingest` with its own token; credentials
  never leave the user's machine). All three converge on one idempotent
  upsert + outbox path.
- **Connectors are data** — `connectors/*.yaml` (generic_rest, braze) drive
  the schema-generated wizard (RJSF) end to end.
- **Forecast + EDA** — SARIMA/ETS/naive ladder with honest fallback warnings;
  `/eda` surfaced in the UI with plain-language readings.
- **Export** — CSV/JSON/XLSX + shareable expiring links
  (`export_jobs.share_token`, 7-day TTL).
- **Real event path** — outbox → Redis Streams → auto-forecast-on-ingest
  consumer (throttled per metric).
- **Auth + RLS** — dev JWTs when `MULTI_TENANT=true` (`POST /dev/token`);
  RLS policies live in migration 0005 with cross-org isolation tests.
- **Anomaly detection** — residual-threshold detector (guide §5.7): actuals
  landing outside the latest forecast's confidence band become `anomalies`
  rows with severity, surfaced on the metric page and as notifications.
- **Notifications** — forecast completions, anomalies, connector errors, and
  stale agents land in a notification center with an unread-count bell.
- **Dashboard** — org-wide overview: connectors/metrics/points/forecast
  counts, open anomalies, recent activity feed.
- **Full management** — connector detail page (webhook URL, pause/resume,
  delete with secret revocation, metric add/remove, poll audit history),
  metric editing, forecast history that survives reloads, horizon/model
  pickers.
- **Ops** — structured JSON logs, retry/backoff on polls AND on worker→ml
  dispatch (terminal failure at a cap), runtime connector-job sync, monthly
  partitioning on the high-volume tables (migration 0006) with scheduled
  maintenance.

Next phase: production deployment per `02-deploy-production.md` (Supabase
providers, always-on container host, Kafka/SQS, Vercel) — gated on this build.
