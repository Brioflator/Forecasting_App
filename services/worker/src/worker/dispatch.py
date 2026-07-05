"""Forecast dispatch loop — the forecast_runs row IS the job (doc 1 §5.4).

Polls pending runs with FOR UPDATE SKIP LOCKED (correct with one worker locally
and N workers in production, unchanged), calls ml, writes forecast_points, and
sets the terminal status. `worker` maps a success into the run, a warning into
model_params, and a structured refusal into status='failed'.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import DataPoint, ForecastPointRow, ForecastRun, Metric
from shared.models import ForecastRequest, Point
from worker.forecast_client import ForecastClient, ForecastFailed


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


def dispatch_pending_forecasts(
    session: Session, client: ForecastClient, batch_size: int = 20
) -> int:
    """Claim and process up to `batch_size` pending runs. Returns the count
    processed. Each run is committed independently so one failure can't roll
    back others."""
    pending = session.scalars(
        select(ForecastRun)
        .where(ForecastRun.status == "pending")
        .order_by(ForecastRun.requested_at)
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    ).all()

    processed = 0
    for run in pending:
        run.status = "running"
        session.flush()
        _process_run(session, run, client)
        session.commit()
        processed += 1
    return processed
