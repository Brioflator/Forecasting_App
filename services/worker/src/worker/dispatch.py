"""Forecast dispatch loop — the forecast_runs row IS the job (doc 1 §5.4).

Polls pending runs with FOR UPDATE SKIP LOCKED (correct with one worker locally
and N workers in production, unchanged), calls ml, writes forecast_points, and
sets the terminal status. `worker` maps a success into the run, a warning into
model_params, and a structured refusal into status='failed'.

Transport-level ml failures (connection refused, 5xx) are retried with
exponential backoff and a terminal cap (doc 1 §7): the attempt count and the
next-attempt time ride in model_params so they survive worker restarts, and a
run that keeps failing at the transport level becomes status='failed' instead
of hot-looping against a down ml service forever.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import DataPoint, ForecastPointRow, ForecastRun, Metric
from shared.models import ForecastRequest, Point
from shared.settings import Settings, get_settings
from worker.forecast_client import ForecastClient, ForecastFailed

log = logging.getLogger("worker.dispatch")

ATTEMPTS_KEY = "dispatch_attempts"
NEXT_ATTEMPT_KEY = "next_attempt_at"


def _load_series(session: Session, metric_id) -> list[Point]:
    rows = session.scalars(
        select(DataPoint).where(DataPoint.metric_id == metric_id).order_by(DataPoint.timestamp)
    ).all()
    return [Point(timestamp=r.timestamp, value=r.value) for r in rows]


def _process_run(session: Session, run: ForecastRun, client: ForecastClient) -> None:
    metric = session.get(Metric, run.metric_id)
    if metric is None:
        run.status = "failed"
        run.error_message = "metric no longer exists"
        run.completed_at = datetime.now(tz=UTC)
        return

    series = _load_series(session, run.metric_id)
    request = ForecastRequest(
        series=series,
        horizon=run.horizon,
        model=run.model_type,
        seasonal_period=metric.seasonal_period,
    )
    try:
        result = client.forecast(request)
    except ForecastFailed as exc:
        run.status = "failed"
        run.error_message = exc.detail
        run.completed_at = datetime.now(tz=UTC)
        return

    for point in result["points"]:
        session.add(
            ForecastPointRow(
                forecast_run_id=run.id,
                timestamp=datetime.fromisoformat(point["timestamp"].replace("Z", "+00:00")),
                predicted_value=point["predicted"],
                lower_bound=point.get("lower"),
                upper_bound=point.get("upper"),
            )
        )
    # Persist what the model actually did so the run is reproducible + the UI can
    # surface the fallback warning (doc 3 §2).
    run.model_params = {
        **result.get("model_params", {}),
        "frequency": result.get("frequency"),
        "metrics": result.get("metrics", {}),
        "warning": result.get("warning"),
        "resolved_model": result.get("model"),
    }
    run.status = "completed"
    run.completed_at = datetime.now(tz=UTC)


def _record_transport_failure(run: ForecastRun, exc: Exception, settings: Settings) -> None:
    """Requeue with exponential backoff, or fail terminally at the cap."""
    params = dict(run.model_params or {})
    attempts = int(params.get(ATTEMPTS_KEY, 0)) + 1
    if attempts >= settings.forecast_dispatch_max_attempts:
        run.status = "failed"
        run.error_message = f"ml service unreachable after {attempts} attempts: {exc}"
        run.completed_at = datetime.now(tz=UTC)
        log.error("run %s failed terminally after %d transport errors", run.id, attempts)
        return
    delay = settings.forecast_dispatch_backoff_seconds * (2 ** (attempts - 1))
    params[ATTEMPTS_KEY] = attempts
    params[NEXT_ATTEMPT_KEY] = (datetime.now(tz=UTC) + timedelta(seconds=delay)).isoformat()
    run.model_params = params
    run.status = "pending"
    log.warning(
        "run %s transport failure %d/%d; retrying in %.0fs: %s",
        run.id,
        attempts,
        settings.forecast_dispatch_max_attempts,
        delay,
        exc,
    )


def _backoff_active(run: ForecastRun) -> bool:
    next_at = (run.model_params or {}).get(NEXT_ATTEMPT_KEY)
    if not next_at:
        return False
    try:
        return datetime.fromisoformat(next_at) > datetime.now(tz=UTC)
    except ValueError:
        return False


def dispatch_pending_forecasts(
    session: Session,
    client: ForecastClient,
    batch_size: int = 20,
    settings: Settings | None = None,
) -> int:
    """Claim and process up to `batch_size` pending runs. Returns the count
    processed. Each run is committed independently so one failure can't roll
    back others."""
    settings = settings or get_settings()
    pending = session.scalars(
        select(ForecastRun)
        .where(ForecastRun.status == "pending")
        .order_by(ForecastRun.requested_at)
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    ).all()

    processed = 0
    for run in pending:
        if _backoff_active(run):
            continue  # leave pending; its next-attempt time hasn't arrived
        run.status = "running"
        session.flush()
        try:
            _process_run(session, run, client)
        except Exception as exc:  # noqa: BLE001 — transport-level failure
            session.rollback()  # discard any partial forecast_points
            _record_transport_failure(run, exc, settings)
        session.commit()
        processed += 1
    session.commit()  # release locks on skipped (backoff) rows
    return processed
