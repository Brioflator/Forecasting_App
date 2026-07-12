# Development guide

How to set up, run, test, and change this codebase without tripping the known
hazards. Commands assume the repo root unless noted.

## Setup

```bash
python -m pip install uv            # or however uv is installed on your machine
uv sync --all-packages              # one lockfile installs api, worker, ml, shared
cd frontend && npm install
```

The Python side is a **uv workspace**: `services/api`, `services/worker`,
`services/ml`, and `shared` share the root `uv.lock`. `agent/` is deliberately
**outside** the workspace (it's the independently auditable artifact users run
on their own machines) and has its own tiny pyproject.

## Running the stack

**With Docker** (the intended contributor path):

```bash
cp .env.example .env
make up          # pg, redis, api, worker, ml, frontend
make seed        # demo connector + metric + 48-point backfill → instant forecast
make seed-live   # optional: real CoinGecko / Open-Meteo / Frankfurter connectors
make logs / make down
```

**Without Docker** (native processes): run Postgres 17 and Redis natively (or
set `EVENT_BUS_IMPL=inproc` to drop Redis), create the `forecast` and
`forecast_test` databases, `alembic upgrade head` on both, then start each
service directly:

```bash
uv run alembic upgrade head
uv run uvicorn api.app:app  --port 8000   # services/api
uv run uvicorn ml.app:app   --port 8100   # services/ml
uv run python -m worker.main              # services/worker
cd frontend && npm run dev                # :3000
```

Point `DATABASE_URL` / `REDIS_URL` / `ML_SERVICE_URL` / `API_URL_INTERNAL` at
localhost instead of the compose hostnames. If your machine can't compile
numba/statsforecast, set `FORECAST_ENGINE=legacy` (statsmodels ladder — no
ARIMA, no CV, always flagged low-confidence). Behind a corporate TLS proxy the
services already trust the OS certificate store (`shared/tls.py`); for uv
itself you may need `UV_SYSTEM_CERTS=true`.

Every knob is documented in `.env.example`; the canonical definitions are
`shared/settings.py`.

## Checks — run these before calling anything done

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
TEST_DATABASE_URL=postgresql+psycopg://forecast:forecast@localhost:5432/forecast_test \
  uv run pytest -q
cd frontend && npm run lint && npm run build
```

`make test` bundles the Python three. Test layout:

- **ml tests are pure in-process** — no DB, no HTTP. They always run.
- **api/worker/cross-service tests are DB-backed** and **skip automatically**
  when `TEST_DATABASE_URL` is unset. The test DB is migrated once per session
  and truncated between tests.
- `shared`'s tests live at **`tests/shared/`**, not `shared/tests/` — pytest's
  importlib mode would otherwise shadow the installed `shared` package with a
  namespace package.
- New behavior needs a test that fails without the change and passes with it.

## Golden files (the ml regression net)

`services/ml/tests/golden/*.json` pin input series + full expected responses;
`test_golden.py` compares numeric fields with `pytest.approx(rel=1e-3)` and
everything else exactly. This is what lets dependencies be upgraded without
silently changing forecasts.

- `make regen-golden` deliberately rewrites the fixtures — **always review the
  diff as a behavioral change review**, never regenerate to make a red test
  green without understanding why it moved.
- `statsforecast` is exact-pinned (`services/ml/pyproject.toml`) because the
  numba-compiled model code shifting under us breaks determinism. Bump it
  deliberately: change the pin → `make regen-golden` → review. `numpy<2` is
  kept until deliberately lifted.

## Migrations discipline

- **SQL-first**: the hand-written SQL in `migrations/versions/` is the schema
  authority; Alembic is only the runner. Never `--autogenerate`.
- `shared/db/models.py` is a hand-maintained mirror. Adding a column is a
  two-step discipline: write the migration, then update the model (and the
  matching `StrEnum` in `shared/domain.py` if it's an enumerated value).
- If a migration file is **rewritten after a database recorded it as
  applied**, recreate that database — Alembic will not re-run it.
- Current chain: 0001 extensions + `auth.users` shim → 0002 core tables →
  0003 team/billing/ops → 0004 outbox + anomalies/LLM → 0005 RLS policies →
  0006 partitioning (`ensure_month_partitions`) → 0007 notification types →
  0008 forecast trust (`low_confidence`, `backtest`) → 0009 perf indexes.

## Known gotchas (each has bitten before)

1. **ML fallback is visible, not silent** — check `low_confidence` +
   `confidence_reasons` (and the returned model name) when debugging forecast
   quality; the pipeline lands on the naive floor on *any* engine failure.
2. **`regularize()` must use the resampler's own bucket labels**, never a
   `date_range` anchored at the first raw timestamp — unaligned webhook
   timestamps otherwise produce an all-NaN series.
3. **Resource budgets move together**: fit window / search bounds
   (`services/ml/src/ml/constants.py`) and concurrency/timeouts were sized as
   a set after an OOM incident. Never raise one without the others.
4. **Reduced motion**: never strip Motion `variants`; toggle only
   `initial={reduceMotion ? false : "hidden"}` (JSDoc in
   `frontend/lib/motion.ts`).
5. **Never rebuild `.next` under a running `next start`** — stop the server
   first.
6. **Demo connector + SSRF**: the seeded demo polls the api's own
   `/dev/sample-metric`, which the SSRF guard would reject;
   `CONNECTOR_ALLOW_PRIVATE_HOSTS` therefore defaults true only when
   `APP_EDITION=local`.
7. **graphify**: a knowledge graph lives at `graphify-out/`. For codebase
   questions prefer `graphify query "<question>"`; after modifying code run
   `graphify update .` to keep it current.

## Conventions

- Match the existing style of the file you're editing; comments state
  constraints and *why*, never narrate the next line.
- Domain strings come from `shared/domain.py`; policy numbers from a
  `constants.py`; configuration from `shared/settings.py` — no magic literals
  in route/loop bodies.
- Work on `develop`; `master` is the release branch (develop → master).
- Keep the docs in `docs/` true in the same commit that changes behavior.
