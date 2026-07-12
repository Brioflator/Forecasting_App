# The worker service

`services/worker` is the always-on process. Locally it is **one process running
several independent loops**; the module boundaries are kept clean so production
can split them into separate replicas without restructuring. `main.py` wires
everything:

| Loop / job | Module | Cadence | What it does |
|---|---|---|---|
| Pull polling | `poller.py` | per-connector cron (APScheduler) | Fetch source, extract, ingest |
| Connector-job sync | `main.sync_pull_jobs` | every `CONNECTOR_SYNC_INTERVAL_SECONDS` (30s) + at startup | Reconcile scheduler jobs against the `connectors` table |
| Forecast dispatch | `dispatch.py` | every `FORECAST_POLL_INTERVAL_SECONDS` (2s) | Claim pending `forecast_runs`, call ml, persist results |
| Outbox relay | `relay.py` | every `OUTBOX_POLL_INTERVAL_SECONDS` (2s) | Publish unpublished `outbox_events` to the EventBus |
| Event consumers | `consumers.py` | bus-driven | Auto-forecast-on-ingest |
| Anomaly sweep | `anomalies.py` | every `ANOMALY_SWEEP_INTERVAL_SECONDS` (60s; 0 disables) | Flag actuals outside the latest forecast band |
| Agent staleness | `maintenance.py` | every minute | Flip silent agents to `stale` + notify once |
| Partition upkeep | `maintenance.py` | daily 02:30 | `ensure_month_partitions` for the partitioned tables |

Startup order in `main()`: configure logging → trust the OS cert store
(`shared/tls.py`, required behind corporate TLS interception) → build the
extractor registry → sync pull jobs (synchronously, before loops start) →
register maintenance jobs → start the scheduler → build **one** EventBus shared
by relay (publisher) and consumers (subscriber) → start the dispatch and relay
threads → install SIGTERM/SIGINT handlers that flip a stop event so `docker
stop` drains cleanly instead of killing mid-poll.

## Scheduling & job sync

`sync_pull_jobs` loads all non-paused `pull` connectors and registers one
APScheduler cron job per connector (`schedule_cron`, falling back to
`DEFAULT_CADENCE_CRON`). It runs on an interval too, so connectors
created/paused/edited through the wizard start or stop polling **without a
worker restart** (jobs are re-added with `replace_existing`, which never delays
the next run because cron triggers fire on wall-clock boundaries). A malformed
cron doesn't crash startup: the connector is skipped, logged, and flipped to
`error`.

## Polling (`poller.py`)

Per connector tick: load its metrics → fetch the secret from the
`SecretsProvider` **at call time** (a missing secret is a run failure, not a
crash) → for each metric, merge `connector.config` with the metric's
`extraction_config` and call the extractor with retry (`POLL_RETRY_ATTEMPTS`=3,
exponential backoff) → `upsert_points` → write a `connector_runs` audit row.

Failure handling: the run is recorded `failed` with the error; after
`MAX_CONSECUTIVE_FAILURES` (5) failed runs in a row the connector flips to
`error` and a `connector_error` notification is raised **once, on the
transition**. A subsequent good poll clears the error state back to `active`.
Errors never propagate out of `poll_connector` — the scheduler must keep
running.

Extractors and the SSRF guard are documented in
[connectors-and-agent.md](connectors-and-agent.md).

## Forecast dispatch (`dispatch.py`)

The `forecast_runs` row is the job (no queue, no Celery — doc 01 §5.4):

1. `SELECT … WHERE status='pending' ORDER BY requested_at FOR UPDATE SKIP
   LOCKED LIMIT batch` — correct with one worker locally and N replicas later.
2. Rows whose backoff window hasn't arrived are skipped (see below); the rest
   flip to `running`.
3. The series payload is the **newest `FORECAST_MAX_SERIES_POINTS` (5000)
   points** (history grows forever; the payload must not — ml caps again at
   512 for fitting). `metrics.seasonal_period` rides along.
4. `HttpForecastClient` POSTs to ml with a **120s read timeout** — generous on
   purpose: timing out a bounded fit mid-flight only to retry the identical fit
   is how work used to pile up on ml (the OOM incident).
5. Outcomes:
   - **Success** → `forecast_points` rows; `model_params` gets the resolved
     model, frequency, diagnostics, and warning (so the run is reproducible
     and the UI can surface the caveat); `low_confidence` and the `backtest`
     JSON (route, candidates, reasons, profile, fit_config) get their own
     columns (migration 0008); status `completed`; a `forecast_completed`
     notification.
   - **Structured refusal** (ml 422 — insufficient/rejected/invalid) →
     terminal `failed` with the detail. Never retried.
   - **Transport failure** (connect error, 5xx incl. ml's 503 load-shed,
     timeout) → the partial transaction is rolled back, then the run goes back
     to `pending` with the attempt count and next-attempt time stored **inside
     `model_params`** so backoff survives worker restarts. Exponential backoff
     from `FORECAST_DISPATCH_BACKOFF_SECONDS` (5s); terminal `failed` after
     `FORECAST_DISPATCH_MAX_ATTEMPTS` (5) so a down ml service is never
     hot-looped forever.
6. Each run commits independently — one failure can't roll back the batch.

## Outbox relay & consumers

`relay.py`: `SELECT … WHERE published_at IS NULL … FOR UPDATE SKIP LOCKED`,
publish to the EventBus, stamp `published_at`. At-least-once by construction;
multi-relay safe.

`consumers.py` — auto-forecast-on-ingest, the consumer that makes the event
path real: on `data_point.ingested`, enqueue a `forecast_runs(model='auto')`
row for the metric **unless** one is already pending/running or one was
requested within `AUTO_FORECAST_MIN_INTERVAL_MINUTES` (15; 0 disables). That
throttle is also the idempotency guard for redelivered events. A consumer
exception is logged and swallowed — it must not kill the bus thread.

## Anomaly sweep (`anomalies.py`)

Per metric: newest **completed** run; skip if `low_confidence` (a
baseline-quality band says nothing about anomalies — alerting off it is a
false-positive storm). Join actuals to forecast points on timestamp; an actual
outside `[lower, upper]` becomes an `anomalies` row. Severity = distance
outside the band relative to band width (`>1.0` band-widths → high, `>0.25` →
medium, else low). Dedupe on existing `(metric_id, detected_at)` keeps sweeps
idempotent; one `anomaly_detected` notification per sweep per metric carries
the count and worst severity.

## Maintenance (`maintenance.py`)

- `ensure_partitions`: calls the SQL function `ensure_month_partitions` (from
  migration 0006) for `data_points`, `connector_runs`, `audit_log`, keeping 3
  months of partitions ahead. On Supabase, pg_partman takes this over.
- `mark_stale_agents`: agents with a heartbeat older than
  `AGENT_STALE_AFTER_MINUTES` (5) flip `active → stale` with one
  `agent_unreachable` notification per transition. (Ingest/heartbeat flips
  them back — see api docs.)

## Adding work to the worker

- **A new periodic job**: add a function module, register it in
  `_register_maintenance_jobs` (or a sibling) with an explicit trigger and job
  id; make it take a `Session` so it's testable without the scheduler; make it
  idempotent.
- **A new event consumer**: subscribe in `register_consumers`; consumers must
  be idempotent (at-least-once delivery) and must swallow their own exceptions.
- **A new loop**: follow `_dispatch_loop`'s shape — own thread, own session per
  iteration, catch-all that logs and continues, honors the stop event.
- Every loop takes a batch size and every external call a timeout; keep it
  that way.

Tests are in `services/worker/tests/` (DB-backed, skip without
`TEST_DATABASE_URL`); the dispatch/poller/consumer/anomaly suites are the
behavioral spec for the flows above. The ml client is exercised through an
ASGI transport so the real serialization path runs without a network server.
