# Forecast Platform

Self-hostable metric collection + forecasting: connectors collect data on a schedule, a stateless ml service routes each series to a StatsForecast model zoo (AutoARIMA/AutoETS/AutoTheta/Croston + naive baselines), backtests candidates with rolling-origin CV, and returns forecasts with confidence intervals and an explicit low-confidence flag; a Next.js frontend charts and exports them. Master spec: `forecast-platform-project-guide.md`; build guides `01`–`05` (local build, production deploy, ml service, frontend, implementation plan).

Scope boundary: the local/open-source product (POC + MVP + full-product layer) is complete. Production deployment — Supabase providers, Kafka/SQS, container hosting (doc `02`) — is intentionally not started; those providers raise `NotImplementedError` by design. Do not begin doc 02 work unless explicitly asked.

## Layout

- uv workspace (one root lockfile), members: `services/api` (FastAPI), `services/worker` (APScheduler poller + dispatch + outbox relay), `services/ml` (stateless forecasting, no DB), `shared`, `agent` (standalone push-agent subtree).
- Everything cloud-swappable sits behind provider interfaces in `shared/providers/`, selected by `APP_EDITION` (+ per-concern overrides) in `shared/factory.py`.
- `migrations/` — SQL-first Alembic. `frontend/` — Next.js App Router. Cross-service tests in `tests/`; per-service tests under each service. Note: `shared`'s tests live at `tests/shared`, NOT `shared/tests` (pytest importlib mode — a `tests/` dir under a dir named like an installed package shadows it with a namespace package).

## Commands

```bash
python -m uv sync --all-packages                 # install the whole workspace
python -m uv run ruff check . && python -m uv run ruff format --check .
python -m uv run mypy
TEST_DATABASE_URL=postgresql+psycopg://...:.../forecast_test python -m uv run pytest -q
```

- DB-backed api/worker tests skip automatically when `TEST_DATABASE_URL` is unset; ml tests are pure in-process (golden files — `make regen-golden` rewrites them, always review the diff).
- Frontend: `npm run dev` / `npm run build` / `npm run lint` in `frontend/`; `npm run gen:api` regenerates `lib/api-schema.d.ts` from a running api.
- `make up` / `make seed` need Docker Compose — see `CLAUDE.local.md` for machines without it.

## Workflow

- Work on `develop`; merge develop → master for releases.

## Gotchas

- `statsforecast` is pinned exactly (`services/ml/pyproject.toml`) — golden-file determinism depends on the numba-compiled model code not shifting. Bump deliberately, then `make regen-golden` and review the diff. pmdarima was removed with it went the old `scikit-learn<1.6` pin; `numpy<2` is kept until deliberately lifted.
- The ml pipeline lands on the naive floor on ANY engine failure, and NaN diagnostics are dropped before JSON — but fallback is no longer silent: check `low_confidence` + `confidence_reasons` on the response (and the returned model name).
- `FORECAST_ENGINE=legacy` runs the statsmodels ladder (no ARIMA rung, no CV, always `low_confidence`) for machines where statsforecast/numba can't install.
- `regularize()` in ml must use `resample()`'s own bucket labels, never a `date_range` anchored at the first raw timestamp — unaligned webhook timestamps otherwise produce an all-NaN series.
- If an Alembic migration file is rewritten after a database already recorded it as applied, recreate that database — Alembic will not re-run it.
- Frontend motion: never strip Motion `variants` for `prefers-reduced-motion` (SSR'd hidden styles then stay invisible forever). Toggle only `initial={reduceMotion ? false : "hidden"}` — the full rule is in the JSDoc of `frontend/lib/motion.ts`.

## graphify

This project has a knowledge graph at `graphify-out/` with god nodes, community structure, and cross-file relationships.

- For codebase questions, first run `graphify query "<question>"` when `graphify-out/graph.json` exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
