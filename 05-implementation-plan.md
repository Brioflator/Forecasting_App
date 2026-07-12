# Forecast Platform — Build Guide 5: Implementation Plan & Last-Mile Specs

> **Status: executed.** The POC (§3) and MVP (§4) sequences are complete, plus
> the full-product layer beyond them (anomaly detection, notifications,
> dashboard, management UI, trust layer). This file remains useful as the
> record of the build order and the pinned last-mile decisions (§2's provider
> signatures, config surface, and ml helper definitions are still accurate,
> except that the ml engine has since moved from pmdarima to StatsForecast —
> see [`docs/ml.md`](docs/ml.md)). The next phase is doc 02 (production
> deployment), which is **intentionally not started**. Current-state
> reference: [`docs/`](docs/README.md).

> **What this document is.** The autonomous build entry point. Documents 1–4 are *reference specs* organized by concern (why / local / deploy / ml / frontend). This document is the *build order* — a dependency-sequenced task list an implementer follows top-to-bottom — plus the handful of concrete "last-mile" specifics the reference docs left to implementer judgment (the exact provider interface signatures, the enumerated configuration surface, the `ml` helper algorithms, and the demo data source). It exists so a coding agent can implement the whole application without guessing, and without two services guessing *differently*.
>
> Consistent with `forecast-platform-project-guide.md` ("the guide"), `01` (local build), `02` (deploy), `03` (ml service), `04` (frontend). Where this document pins a value that "belongs" in an earlier doc, it says so — the pattern doc 1 §12 already established for recorded addenda. **Anything pinned here is a sensible default chosen to be buildable, not doctrine; the maintainer adjusts in refinement.**

---

## 0. How to use this document

Read order for an implementer new to the project:

1. **This document §1** — confirm you actually have all five source documents. This plan cites them constantly (e.g. "doc 3 §6"); without them those cross-references are dangling and large parts of the plan are unusable.
2. **Guide §8 (POC Requirement Sheet)** — the scope of the first milestone, and the guide's own designated starting point.
3. **This document §2** — the last-mile specs (interfaces, config, `ml` helpers, test tooling, demo source) that the reference docs left open. Read before writing code; they remove the remaining ambiguity.
4. **This document §3** — the POC build sequence. Follow it in order; each step lists its file targets and its acceptance check.
5. **Docs 1 / 3 / 4** as the deep reference for each step (schema, service contracts, ml ladder, frontend screens).
6. **This document §4** — the MVP delta once the POC acceptance gate (guide §8) is green.
7. **Doc 2** only after the local MVP is fully functional (its own prerequisite).

The golden rule from doc 1 §2 holds throughout: **no service imports a concrete provider directly** — everything cloud-swappable goes through an interface resolved by the `shared` factory on `APP_EDITION`.

---

## 1. Required inputs — the documents this plan depends on

This plan is deliberately cross-referential: it does not restate the schema, the ml ladder, or the service contracts — it *points* at them. Before writing any code, confirm all of the following are present in your context or on the filesystem alongside this file. **If any is missing, stop and load it** — a citation like "doc 3 §6" is worthless without doc 3, and this plan's precision depends on them.

| Ref used here | File (in `P:\Forecast_App`) | What it authoritatively owns |
|---|---|---|
| "the guide" | `forecast-platform-project-guide.md` | product rationale, the full DB schema (§5), POC/MVP scope (§8/§9) |
| "doc 1" | `01-build-local-opensource.md` | local architecture, provider seam, migrations policy (§4.2), inter-service contracts (§5), schema addenda (§12) |
| "doc 2" | `02-deploy-production.md` | production provider swaps — **not used until the local MVP gate holds** |
| "doc 3" | `03-forecasting-and-ml-service.md` | the ml service — model ladder, thresholds, messy-data handling, tests |
| "doc 4" | `04-frontend.md` | frontend stack, screens, the two structural ADRs |

Those five plus this document (`05`) are the **complete** input set — there are no other required documents. If you can read this file, the other five should be in the same folder; verify their presence before relying on any cross-reference rather than reconstructing a cited section from memory.

---

## 2. Last-mile specifications (authoritative)

### 2.1 The provider interfaces — all four, complete

Doc 1 §2.1 shows `EventBus` and the guide §7.3 shows `SecretsProvider`. The other two are pinned here so the seam is fully specified. All live in `shared/providers/`, all are `typing.Protocol`s, all selected by the `shared/factory.py` `make_*` functions keyed on `APP_EDITION` + per-concern override (doc 1 §2).

```python
# shared/providers/secrets.py           (guide §7.3, restated for completeness)
class SecretsProvider(Protocol):
    def get_secret(self, tenant_id: str, secret_key: str) -> str: ...
    def put_secret(self, tenant_id: str, secret_key: str, value: str) -> None: ...
    def revoke_secret(self, tenant_id: str, secret_key: str) -> None: ...

# shared/providers/event_bus.py         (doc 1 §2.1, restated)
class EventBus(Protocol):
    def publish(self, topic: str, payload: dict) -> None: ...
    def subscribe(self, topic: str, handler: Callable[[dict], None]) -> None: ...

# shared/providers/blob_store.py        (NEW — pinned here)
class BlobStore(Protocol):
    def put(self, path: str, data: bytes, content_type: str) -> str: ...   # returns stored object path
    def get(self, path: str) -> bytes: ...
    def signed_url(self, path: str, expires_in: int) -> str: ...           # seconds; powers export share links
    def delete(self, path: str) -> None: ...

# shared/providers/auth.py              (NEW — pinned here)
@dataclass(frozen=True)
class Principal:
    org_id: str
    user_id: str
    role: str            # 'owner' | 'admin' | 'member'  (guide §5 organization_members.role)

class AuthProvider(Protocol):
    # api calls this on every request; raises Unauthorized on a bad/absent token.
    def authenticate(self, authorization_header: str | None) -> Principal: ...
```

Local implementations:
- `LocalBlobStore` — writes under `EXPORT_DIR` (a mounted `./data/exports` volume); `signed_url` returns `{API_URL}/exports/{share_token}` (the token *is* the capability locally, doc 1 §6.5).
- `LocalAuthProvider` — ignores the header, always returns the fixed implicit `Principal` seeded by `make seed` (doc 1 §6.6). When `MULTI_TENANT=true` locally, it instead validates a dev JWT so the multi-tenant path is exercisable.

Production implementations (`SupabaseBlobStore`, `SupabaseVaultSecretsProvider`, `SupabaseAuthProvider`, `KafkaEventBus`/SQS-SNS) are doc 2 §4 and are **not** built during the local milestones — but their `case` in the factory should exist and raise `NotImplementedError` so the seam shape is visible from day one.

### 2.2 The shared DTOs

`shared/models/` holds the Pydantic models that are the inter-service contracts. Derive them directly from the JSON shapes already specified — this table is the index, the linked sections are authoritative:

| Model | Fields | Source of truth |
|---|---|---|
| `Point` | `timestamp: datetime`, `value: float` | doc 1 §4.1, doc 3 §2 |
| `ForecastRequest` | `series: list[Point]`, `horizon: int`, `model: str = "auto"`, `seasonal_period: int \| None`, `model_params: dict = {}`, `confidence: float = 0.95` | doc 3 §2 |
| `ForecastPoint` | `timestamp`, `predicted`, `lower`, `upper` | doc 3 §2 |
| `ForecastResponse` | `model`, `model_params`, `frequency`, `points: list[ForecastPoint]`, `metrics: dict`, `warning: str \| None` | doc 3 §2 |
| `ForecastError` | `error`, `detail`, `min_required` | doc 3 §2 |
| `EdaRequest` / `EdaResponse` | per doc 3 §2 | doc 3 §2 |
| `IngestPayload` | `metric_key: str`, `points: list[Point]` | doc 1 §5.3 |

`ml` depends on **none** of the DB models — it imports only these DTOs (keeps it pure, doc 3 §0).

### 2.3 The configuration surface (`.env.example`, enumerated)

Doc 1 promises "`.env.example` — every knob, documented, with local-safe defaults" but never lists them. This is the canonical set. Names are pinned so all three services and the frontend agree; the `shared` settings object (a `pydantic-settings` `BaseSettings`) reads them.

```bash
# ── Edition & providers (the seam selectors, doc 1 §2) ───────────────
APP_EDITION=local                 # local | production
SECRETS_IMPL=dotenv               # dotenv | supabase_vault
EVENT_BUS_IMPL=redis              # inproc | redis | kafka
BLOB_STORE_IMPL=local             # local | supabase
AUTH_IMPL=local                   # local | supabase
MULTI_TENANT=false                # local flag to exercise real auth/RLS (doc 1 §6.6)

# ── Datastores ───────────────────────────────────────────────────────
DATABASE_URL=postgresql+psycopg://forecast:forecast@postgres:5432/forecast
REDIS_URL=redis://redis:6379/0

# ── Service wiring ───────────────────────────────────────────────────
API_PORT=8000
ML_PORT=8100
ML_SERVICE_URL=http://ml:8100     # worker → ml (doc 1 §3.1)
API_URL=http://localhost:8000     # for building share links locally
CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=info

# ── Secrets / storage (local impls) ──────────────────────────────────
SECRET_FILE=/run/secrets/connectors.env   # DotenvSecretsProvider source (gitignored)
EXPORT_DIR=/data/exports                    # LocalBlobStore root

# ── worker knobs ─────────────────────────────────────────────────────
FORECAST_POLL_INTERVAL_SECONDS=2   # how often worker sweeps forecast_runs (doc 1 §5.4)
OUTBOX_POLL_INTERVAL_SECONDS=2     # outbox relay sweep (doc 1 §6.2)
POLL_BATCH_SIZE=20                 # rows per SKIP LOCKED batch
DEFAULT_CADENCE_CRON=* * * * *     # demo-friendly: every minute (doc 1 §6.1)
MAX_CONSECUTIVE_FAILURES=5         # flips connector.status to 'error' (doc 1 §7)

# ── ml knobs (doc 3 §4–§5) ───────────────────────────────────────────
FORECAST_DEFAULT_CONFIDENCE=0.95
GAP_FILL_MAX_CONSECUTIVE=3         # doc 3 §5 bounded fill
GAP_FILL_MAX_FRACTION=0.05         # doc 3 §5 over-sparse flag threshold
AUTO_ARIMA_MAX_P=5                 # bound the stepwise search (doc 3 §6 latency)
AUTO_ARIMA_MAX_Q=5

# ── production only (doc 2) — present but unused when APP_EDITION=local ─
# SUPABASE_URL=            SUPABASE_ANON_KEY=            SUPABASE_SERVICE_ROLE_KEY=
# SUPABASE_JWT_SECRET=     KAFKA_BROKERS=  (or AWS_REGION + SQS/SNS ARNs)
```

Frontend env (doc 4 §4), separate `.env` in `/frontend`:

```bash
NEXT_PUBLIC_APP_EDITION=local
NEXT_PUBLIC_API_URL=http://localhost:8000
# production only:
# NEXT_PUBLIC_SUPABASE_URL=   NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

### 2.4 `ml` helper algorithms — the stubs in doc 3 §6, pinned

Doc 3 §6 sketches `forecast()` and `_sarima()` fully but leaves `autodetect_period`, seasonality strength, the non-SARIMA executors, naive intervals, and `_mape` as named helpers. Pinned here so golden-file outputs (doc 3 §7) are reproducible. All deterministic. Constants live beside the doc 3 §6 thresholds.

**`autodetect_period(s) -> int | None`** — candidate-ACF method (deterministic, cheap, no FFT tuning):
1. Candidate periods from common cadences: `[24, 168, 7, 12, 52, 4, 30]` (hourly-daily, hourly-weekly, daily-weekly, monthly-yearly, weekly-yearly, quarterly, monthly-ish). Keep only candidates `≤ len(s) // 2`.
2. Difference the series once (remove trend), compute the autocorrelation at each candidate lag.
3. Pick the candidate with the highest ACF **if** it exceeds `SEASONALITY_ACF_THRESHOLD = 0.3`; else return `None` (treat as non-seasonal).
This is intentionally conservative — a real per-metric period should come from `metrics.seasonal_period` (doc 1 §12.1); auto-detection is the fallback when that's `NULL`.

**Seasonality strength (for `/eda`)** — the standard STL-based measure (Wang–Hyndman): decompose with `statsmodels` STL at the detected/provided period, then `strength = max(0, 1 - Var(remainder) / Var(remainder + seasonal))`, clamped to `[0, 1]`. `> 0.6` → "strong", `0.3–0.6` → "moderate", `< 0.3` → "weak/none" for the `plain` reading.

**The ladder executors** (doc 3 §3), each returns a `ForecastResult` with model-derived intervals:
- `_holt_winters(s, horizon, m, ...)` → `statsmodels ExponentialSmoothing(trend="add", seasonal="add", seasonal_periods=m)`; intervals from the fitted model's simulation or forecast standard errors.
- `_ets_trend(s, horizon, ...)` → `ExponentialSmoothing(trend="add", seasonal=None)`.
- `_seasonal_naive(s, horizon, m, ...)` → if `m` known: repeat the last full seasonal cycle forward; else **drift**: `ŷ_{n+h} = y_n + h · (y_n − y_1)/(n−1)`. Intervals: `ŷ ± z · σ̂ · √h`, where `σ̂` is the std of the in-sample one-step naive residuals and `z` from `confidence`. This is the honest "wide bands on a short series" behavior doc 3 §3 wants.

**`_mape(model, s)`** — mean absolute percentage error of in-sample one-step predictions vs actuals; **switch to sMAPE** (`mean(2|a−f| / (|a|+|f|))`) when any actual is near zero, to avoid division blowups. Reported in `metrics.in_sample_mape` for the UI's model diagnostics.

**Ladder clarification** — doc 3 §6 line 193 references `_plausible_cycle`; pin the ladder crisply to remove it: once `m` is established (passed in or auto-detected), the only length gate is `2m`. So:

```
if m and len(s) >= 2*m:      try _sarima; on fit failure → _holt_winters(same data, warn=fell back)
elif len(s) >= TREND_MIN:    _ets_trend  (warn: not enough data for seasonal)
else:                        _seasonal_naive / drift  (warn: very short series)
```

`_holt_winters` is thus the *in-family fallback* when a SARIMA fit fails at sufficient length — not a separate length rung. This matches doc 3 §3's intent (always return the richest model the data supports) with one fewer undefined helper.

### 2.5 The demo data source (so the POC loop runs offline)

Guide §8 success criteria need "a real API you control" for the demo. To keep `docker compose up` self-contained (doc 1 non-functional: no cloud account, runs offline), `api` ships a **local-only** dev endpoint plus a seeded backfill.

- `GET /dev/sample-metric` — returns `{"value": <float>, "timestamp": <ISO>}` where value follows a **fixed sinusoid of period 12 points + seeded noise**. Enabled only when `APP_EDITION=local`; returns 404 otherwise.
- **Pin the demo's seasonality explicitly — do not leave `m` implicit.** Three numbers are matched on purpose: the synthetic signal's period is **`m = 12`**, the seeded metric is created with **`seasonal_period = 12`**, and the connector cadence is **every minute** (`DEFAULT_CADENCE_CRON`). Because the SARIMA floor is `2m` (doc 3 §4), `m = 12` means only **24 points** are needed for a real SARIMA fit. A large `m` (24/168) against a per-minute cadence would push the guide §8 "returns a plausible SARIMA result" gate to hours and look broken — the mismatch the vague "matched to the synthetic pattern" phrasing previously invited.
- **`make seed` backfills history so the gate is instant and deterministic**, not cadence-dependent: it inserts **~4 full cycles (≈48 points, `source='backfill'`) ending at "now"** of the same synthetic signal, so a SARIMA forecast is available on the *first* metric-detail load, before any live poll. Live polling then keeps appending. This makes the §8 acceptance check a one-shot reproducible verification rather than a "wait ~24 minutes and hope" timing race — which matters when an automated build is verifying its own gate.
- The seeded connector: `generic_rest` targeting `{API_URL}/dev/sample-metric`, `value_path=$.value`, `timestamp_path=$.timestamp`; one metric `key=sample_signups`, `seasonal_period=12`, 1-minute cadence.

### 2.6 Test tooling (pinned)

Pinned so the golden-file mechanism (doc 3 §7) is identical across sessions — an agent must not invent one here and a different one three sessions later.

- **Runner:** `pytest`, exact-pinned to a recent 8.x in `uv.lock`. It is the only test framework, across all services.
- **Golden files for `ml`:** committed JSON fixtures under `services/ml/tests/golden/`, one file per case (input series + pinned request params + expected response). The test loads the fixture, calls `forecast()` / `eda()` **in-process** (no HTTP, no DB), and compares **numeric fields with `pytest.approx(rel=1e-3)`** — a tolerance that absorbs BLAS/library micro-differences but catches real behavioral drift (doc 3 §7). Non-numeric fields (`model`, `warning`, `frequency`) compared exactly. **Committed-JSON + `pytest.approx` is chosen deliberately over a snapshot library (syrupy):** regeneration must be an explicit, reviewable `make regen-golden` script that rewrites fixtures so a human eyeballs the diff — never a test-run auto-accept that silently blesses a changed forecast.
- **DB-touching tests (`api` / `worker`):** run against the compose Postgres using a dedicated test database, migrated once per session and truncated between tests. **Do not add testcontainers** — the compose stack *is* the environment, and pulling it in fights the "one command" promise. `ml` tests must not open a DB at all (it's the statelessness payoff, doc 3 §7).
- **Type/lint gate:** `ruff` (format + lint) and **`mypy`** run clean as part of `make test`. The guide §4.2 library table pins **mypy** as the type checker; Astral's `ty` is faster but was still pre-release/unstable in early 2026 — treat it as a future drop-in once stable, **not** part of the initial build. (This corrects step 1's earlier "`ty`" mention.)

---

## 3. POC build sequence (guide §8 scope)

Dependency-ordered. Each step is independently runnable/testable before the next. Scope boundary is guide §8 "In scope / Explicitly out of scope" — no auth enforcement, no push/agent, no queue, pull-only, single implicit org.

| # | Step | Primary targets | Done when |
|---|---|---|---|
| 1 | **Workspace scaffold** | root `pyproject.toml` (uv workspace), `services/{api,worker,ml}/pyproject.toml`, `shared/pyproject.toml`, `uv.lock` | `uv sync` installs all four members; `ruff` + **`mypy`** run clean (type checker is mypy per §2.6 — **not** the still-prerelease `ty`) |
| 2 | **shared: settings + provider seam** | `shared/settings.py` (§2.3), `shared/providers/*` (§2.1), `shared/factory.py`, `shared/models/*` (§2.2) | factory returns `inproc`/`dotenv`/`local` impls under `APP_EDITION=local`; unit-tested |
| 3 | **DB migrations (SQL-first)** | `migrations/` Alembic runner + `0001…0004` per doc 1 §12.3 (extensions+auth shim → core → team/ops → outbox/anomaly), incl. the §12.1 `metrics.key`/`seasonal_period` columns | `alembic upgrade head` succeeds against the compose Postgres. **POC scope: hand-write `0001`–`0004` only. Create `0005` (RLS) and `0006` (partitioning/`pg_partman`) as empty placeholder migrations and do NOT author them now** — they're inert with one implicit org, and declarative-partition + `pg_partman` DDL is the single most error-prone thing for an LLM to hand-write, exactly where models drift from migrations. They get written *and tested* in the MVP step that actually turns them on (§4). "upgrade head succeeds" is not a sufficient check for RLS correctness, so don't chase it here. |
| 4 | **SQLAlchemy mapping models** | `shared/db/models.py` mirroring the tables (doc 1 §4.2 — hand-maintained, not autogenerated) | models round-trip against the migrated schema in a test |
| 5 | **ml service** | `services/ml/` — `forecasting.py` (doc 3 §6 + §2.4 here), `eda.py`, FastAPI app with `/forecast`, `/eda`, `/healthz` | doc 3 §7 test suite green (golden-file mechanics pinned in §2.6): ladder-coverage, regularization, golden-file, contract tests. **This is the product core — build and test it in isolation first; it needs no DB.** |
| 6 | **api service (POC subset)** | `services/api/` — connector CRUD, metric CRUD, `GET /metrics/{id}/data`, `POST /metrics/{id}/forecast` (inserts `forecast_runs` pending, doc 1 §5.4), `GET /forecasts/{id}`, `GET /forecasts/{id}/export?format=csv`, `GET /dev/sample-metric` (§2.5), `/healthz`; `LocalAuthProvider` injects the implicit org | endpoints work against the DB; **pytest covering connector/metric CRUD and the forecast enqueue→poll lifecycle against the test DB (§2.6) is green**; OpenAPI emitted for frontend codegen (doc 4 §5) |
| 7 | **worker service (POC subset)** | `services/worker/` — APScheduler poller (doc 1 §6.1), `GenericRestExtractor` (doc 1 §4.1 incl. `quantize_to_cadence`), idempotent upsert, `forecast_runs` dispatch loop calling `ml` (doc 1 §5.4). Outbox relay module present but a no-op sink is fine for POC (no consumers yet) — **keep the relay module; do not delete it as "unused", the MVP (§4) wires a real EventBus into it.** | a seeded connector accumulates `data_points` on cadence with no manual action; a forecast request completes end-to-end; **pytest for the extractor (incl. the `quantize_to_cadence` idempotency case: a re-poll yields no duplicate point) and the dispatch loop is green** |
| 8 | **CSV export** | export module in `api` (guide §6.1), `LocalBlobStore` | `GET …/export?format=csv` streams a valid forecast CSV |
| 9a | **Frontend scaffold + typed client** | `/frontend` Next.js App Router shell (doc 4 §3 layout), `lib/api.ts` generated from `api`'s OpenAPI (doc 4 §5), `auth.ts` local seam returning the fixed session (doc 4 §4) | app boots at `localhost:3000`, calls `api`, and renders a raw list of the seeded metric's data points — proving client + generated types + CORS all work end-to-end before any charting |
| 9b | **Metric-detail screen** | `ForecastChart` (doc 4 §7 — actuals + forecast line + CI `Area`, with the `warning` surfaced), metric-detail page, CSV export button, a bare connector list | open the seeded metric → actuals+forecast chart with a confidence band + working CSV download. **This is the guide §8 visual gate.** |
| 10 | **Compose + Make + seed** | `docker/docker-compose.yml` (pg, redis, api, worker, ml, frontend), `Makefile` (`up/seed/test/migrate`), `.env.example` (§2.3), `README` quickstart | **the guide §8 gate:** fresh clone → `cp .env.example .env && make up && make seed` → rendered forecast + downloaded CSV, on 2 GB RAM, no cloud account |

Redis is in the compose stack from step 10 but the POC may run `EVENT_BUS_IMPL=inproc` (doc 1 §6.3) — the outbox/events path isn't load-bearing until the MVP adds consumers.

**Testing is part of each backend step's gate, not a deferred pass.** Steps 2, 4, 5, 6, and 7 each name their test inside "done when" — treat a step as incomplete until those are green, because an agent optimizes to the stated gate and will otherwise skip tests on `api`/`worker`. `ml` (step 5) carries the heaviest suite (doc 3 §7); `api`/`worker` need at least the flows named in their rows. The frontend (9a/9b) is gated **functionally, not by tests** — deliberate, per the maintainer's steer that it need only display the data faithfully (design/UX is a later refinement pass).

---

## 4. MVP build sequence (guide §9 delta)

Everything above stays; layer these on, **still local, no deployment** (guide §9). Order is roughly independent — pick by value:

- **Multi-connector, config-driven** — load all `connector_definitions` from `/connectors/*.yaml` at startup; add `braze.yaml` (doc 1 §4.1). Connector types become data.
- **Push ingestion** — `POST /webhooks/{token}` + `POST /ingest` (doc 1 §5.3), converging on the same normalize→upsert→outbox path as pull (doc 1 §3).
- **Auth + RLS live locally** — set `MULTI_TENANT=true`; `LocalAuthProvider` validates dev JWTs; the RLS policies (migration `0005`) stop being inert. Write the cross-org isolation tests now (doc 2 §4.4) even though enforcement ships for real in doc 2.
- **EDA endpoint surfaced** — wire `ml` `/eda` (doc 3 §2) into `api` + the `EdaReport` component (doc 4 §3), plain-language readings first.
- **Full export** — add JSON + XLSX (guide §6.1, `openpyxl`) and shareable expiring links via `export_jobs.share_token` + `LocalBlobStore.signed_url`.
- **Real event path** — flip `EVENT_BUS_IMPL=redis`; the outbox relay (doc 1 §6.2) publishes `data_point.ingested`; add at least one consumer (e.g. auto-forecast-on-ingest) so the bus is exercised, not theoretical.
- **Agent v1** — the `/agent` subtree (guide §7.7): standalone Docker poller, holds its own credential, `POST /ingest` with a bearer token, heartbeats into `agents`; onboarding wizard emits the pre-filled `docker-compose.agent.yml` (doc 4 §2, §6).
- **Operational basics** — retry/backoff on failed polls, `connector_runs` audit rows, `MAX_CONSECUTIVE_FAILURES` → `status='error'` + notification, structured logging, and enable `pg_partman` on `data_points`/`connector_runs` (migration `0006`) before volume makes it painful.
- **Frontend fill-in** — connector wizard via RJSF (doc 4 §6), dataset list with sparklines, agent-health screen (doc 4 §3). *Kept intentionally minimal per the maintainer's steer; design/UX is a later refinement pass.*

---

## 5. Acceptance gates

- **POC done** = guide §8 success criteria (§3 step 10 above). This is the precondition for opening doc 2.
- **MVP done** = guide §9 capabilities all functional locally via `docker compose up`.
- **Shipped** = doc 2 §12 (real auth, data accumulates with no session open, forecast+EDA+shareable export, every backend service restartable with zero data loss, RLS isolation tests green). **Do not start doc 2 until the MVP gate holds locally** (doc 2 prerequisite).

---

## 6. What this unblocks

With this document, the build has a single ordered path from empty repo to the guide §8 gate, and the five last-mile ambiguities are pinned: all four provider interfaces have signatures, the configuration surface is enumerated with canonical names, every `ml` helper doc 3 named is now defined deterministically (protecting the golden-file tests), and the demo loop runs with no external dependency. Combined with docs 1–4, an implementer — human or agent — can build `shared`, `ml`, `api`, and `worker` end-to-end with no remaining "what did they mean here?" stops, which is exactly where the backend and the forecasting core needed the extra precision. The frontend is specified enough to *display the data faithfully*; its visual/UX direction is deliberately left for the maintainer's refinement pass.
