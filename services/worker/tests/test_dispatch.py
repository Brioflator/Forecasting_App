"""Forecast dispatch loop end-to-end (plan 05 §3 step 7).

Drives the real HttpForecastClient against the ml ASGI app (no network server),
so the worker→ml serialization contract is exercised in-process.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ml import forecasting
from ml.errors import InsufficientData
from shared.db.models import DataPoint, ForecastPointRow, ForecastRun
from shared.models import ForecastRequest
from shared.synthetic import sample_value
from worker.dispatch import dispatch_pending_forecasts
from worker.forecast_client import ForecastFailed


class _InProcessMlClient:
    """Implements the ForecastClient protocol by calling ml in-process, mirroring
    the JSON the real HttpForecastClient returns. The HTTP transport/parsing is
    covered separately by ml's own contract tests; this keeps the dispatch test
    deterministic and network-free."""

    def forecast(self, request: ForecastRequest) -> dict:
        try:
            result = forecasting.forecast(
                series=request.series,
                horizon=request.horizon,
                model=request.model,
                seasonal_period=request.seasonal_period,
                confidence=request.confidence,
            )
        except InsufficientData as exc:
            raise ForecastFailed(str(exc)) from exc
        return {
            "model": result.model,
            "model_params": result.model_params,
            "frequency": result.frequency,
            "points": [
                {
                    "timestamp": p["timestamp"].isoformat(),
                    "predicted": p["predicted"],
                    "lower": p["lower"],
                    "upper": p["upper"],
                }
                for p in result.points
            ],
            "metrics": result.metrics,
            "warning": result.warning,
        }


def _ml_client() -> _InProcessMlClient:
    return _InProcessMlClient()


def _seed_series(db_session: Session, seeded, n: int) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    for i in range(n):
        db_session.add(
            DataPoint(
                metric_id=seeded.metric.id,
                organization_id=seeded.org_id,
                timestamp=base + timedelta(minutes=i),
                value=sample_value(i, m=12),
                source="backfill",
            )
        )
    db_session.flush()


def _enqueue(db_session: Session, seeded, horizon: int = 6, model: str = "auto") -> uuid.UUID:
    run = ForecastRun(
        organization_id=seeded.org_id,
        metric_id=seeded.metric.id,
        model_type=model,
        horizon=horizon,
        status="pending",
    )
    db_session.add(run)
    db_session.flush()
    return run.id


def test_dispatch_completes_a_forecast(seeded, db_session: Session) -> None:
    _seed_series(db_session, seeded, 48)  # ≥ 2 cycles at m=12 → SARIMA
    run_id = _enqueue(db_session, seeded, horizon=6)
    db_session.commit()

    processed = dispatch_pending_forecasts(db_session, _ml_client())
    assert processed == 1

    run = db_session.get(ForecastRun, run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.completed_at is not None
    assert run.model_params.get("resolved_model") == "sarima"

    points = db_session.scalars(
        select(ForecastPointRow).where(ForecastPointRow.forecast_run_id == run_id)
    ).all()
    assert len(points) == 6
    assert all(p.lower_bound <= p.predicted_value <= p.upper_bound for p in points)


def test_dispatch_marks_insufficient_data_failed(seeded, db_session: Session) -> None:
    _seed_series(db_session, seeded, 2)  # below the absolute floor of 4
    run_id = _enqueue(db_session, seeded, horizon=3)
    db_session.commit()

    dispatch_pending_forecasts(db_session, _ml_client())
    run = db_session.get(ForecastRun, run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error_message is not None


def test_dispatch_noop_when_nothing_pending(seeded, db_session: Session) -> None:
    assert dispatch_pending_forecasts(db_session, _ml_client()) == 0


class _RecordingClient:
    """Captures the request the dispatcher builds; returns a minimal success."""

    def __init__(self) -> None:
        self.last_request: ForecastRequest | None = None

    def forecast(self, request: ForecastRequest) -> dict:
        self.last_request = request
        return {
            "model": "ets",
            "model_params": {},
            "frequency": "min",
            "points": [],
            "metrics": {},
            "warning": None,
        }


def test_dispatch_caps_series_payload(seeded, db_session: Session) -> None:
    """The dispatcher must not ship an unbounded, ever-growing history to ml —
    that is what made per-fit cost grow without limit (the crash root cause).
    Only the most recent forecast_max_series_points points are sent, in
    chronological order."""
    from shared.settings import Settings

    _seed_series(db_session, seeded, 80)
    _enqueue(db_session, seeded, horizon=3, model="ets")
    db_session.commit()

    client = _RecordingClient()
    settings = Settings(_env_file=None, forecast_max_series_points=50)  # type: ignore[call-arg]
    dispatch_pending_forecasts(db_session, client, settings=settings)

    assert client.last_request is not None
    sent = client.last_request.series
    assert len(sent) == 50
    # The newest points, oldest→newest.
    timestamps = [p.timestamp for p in sent]
    assert timestamps == sorted(timestamps)
    base = datetime(2026, 7, 1, tzinfo=UTC)
    assert timestamps[0] == base + timedelta(minutes=30)  # 80 - 50
    assert timestamps[-1] == base + timedelta(minutes=79)
