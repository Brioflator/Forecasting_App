"""Residual-threshold anomaly detection (guide §5.7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db.models import Anomaly, DataPoint, ForecastPointRow, ForecastRun, Notification
from worker.anomalies import detect_anomalies


def _completed_forecast(db_session: Session, seeded, base: datetime) -> ForecastRun:
    run = ForecastRun(
        organization_id=seeded.org_id,
        metric_id=seeded.metric.id,
        model_type="auto",
        horizon=4,
        status="completed",
        completed_at=base,
    )
    db_session.add(run)
    db_session.flush()
    for i in range(4):
        db_session.add(
            ForecastPointRow(
                forecast_run_id=run.id,
                timestamp=base + timedelta(minutes=i),
                predicted_value=100.0,
                lower_bound=95.0,
                upper_bound=105.0,
            )
        )
    db_session.commit()
    return run


def _actual(db_session: Session, seeded, ts: datetime, value: float) -> None:
    db_session.add(
        DataPoint(
            metric_id=seeded.metric.id,
            organization_id=seeded.org_id,
            timestamp=ts,
            value=value,
            source="poll",
        )
    )
    db_session.commit()


def test_actual_outside_band_is_flagged_with_severity(seeded, db_session: Session) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    _completed_forecast(db_session, seeded, base)
    _actual(db_session, seeded, base + timedelta(minutes=0), 100.0)  # inside → fine
    _actual(db_session, seeded, base + timedelta(minutes=1), 106.0)  # just above → low
    _actual(db_session, seeded, base + timedelta(minutes=2), 130.0)  # way above → high

    created = detect_anomalies(db_session)
    assert created == 2

    anomalies = db_session.scalars(select(Anomaly).order_by(Anomaly.detected_at)).all()
    assert [a.severity for a in anomalies] == ["low", "high"]
    assert anomalies[0].expected_value == 100.0

    note = db_session.scalar(select(Notification).where(Notification.type == "anomaly_detected"))
    assert note is not None
    assert note.payload["count"] == 2
    assert note.payload["worst_severity"] == "high"


def test_sweep_is_idempotent(seeded, db_session: Session) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    _completed_forecast(db_session, seeded, base)
    _actual(db_session, seeded, base, 200.0)

    assert detect_anomalies(db_session) == 1
    assert detect_anomalies(db_session) == 0  # already flagged, no dupes

    count = db_session.scalar(select(func.count()).select_from(Anomaly))
    assert count == 1
    notes = db_session.scalars(
        select(Notification).where(Notification.type == "anomaly_detected")
    ).all()
    assert len(notes) == 1  # notification only on the sweep that found something


def test_no_forecast_no_anomalies(seeded, db_session: Session) -> None:
    _actual(db_session, seeded, datetime(2026, 7, 1, tzinfo=UTC), 999.0)
    assert detect_anomalies(db_session) == 0
