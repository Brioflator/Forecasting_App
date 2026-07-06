"""Residual-threshold anomaly detection (guide §5.7, v2.x pulled forward).

The statistical layer the guide's market analysis calls the real gap-closer:
an actual observation landing OUTSIDE the latest forecast's confidence band is
an anomaly — the model said "95% sure it'll be in here" and reality disagreed.

Per metric: take the newest completed forecast run, join actual data_points to
forecast_points on timestamp, and flag actuals beyond [lower, upper]. Severity
scales with how far outside the band the point landed relative to the band's
width. Dedupe on (metric_id, detected_at) so sweeps are idempotent, and raise
one anomaly_detected notification per sweep per metric (not per point).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import (
    Anomaly,
    DataPoint,
    ForecastPointRow,
    ForecastRun,
    Metric,
    Notification,
)

log = logging.getLogger("worker.anomalies")

SEVERITY_HIGH_EXCESS = 1.0  # outside by more than one full band-width
SEVERITY_MEDIUM_EXCESS = 0.25


def _severity(value: float, lower: float, upper: float) -> str:
    band = max(upper - lower, 1e-9)
    distance = (lower - value) if value < lower else (value - upper)
    excess = distance / band
    if excess > SEVERITY_HIGH_EXCESS:
        return "high"
    if excess > SEVERITY_MEDIUM_EXCESS:
        return "medium"
    return "low"


def _detect_for_metric(session: Session, metric: Metric) -> int:
    run = session.scalar(
        select(ForecastRun)
        .where(ForecastRun.metric_id == metric.id, ForecastRun.status == "completed")
        .order_by(ForecastRun.completed_at.desc())
        .limit(1)
    )
    if run is None:
        return 0

    # Actuals that landed on forecasted timestamps — the comparable window.
    pairs = session.execute(
        select(DataPoint, ForecastPointRow)
        .join(
            ForecastPointRow,
            (ForecastPointRow.timestamp == DataPoint.timestamp)
            & (ForecastPointRow.forecast_run_id == run.id),
        )
        .where(
            DataPoint.metric_id == metric.id,
            ForecastPointRow.lower_bound.is_not(None),
            ForecastPointRow.upper_bound.is_not(None),
        )
    ).all()
    if not pairs:
        return 0

    existing = set(
        session.scalars(select(Anomaly.detected_at).where(Anomaly.metric_id == metric.id)).all()
    )

    created = 0
    worst = "low"
    order = {"low": 0, "medium": 1, "high": 2}
    for actual, predicted in pairs:
        lower, upper = predicted.lower_bound, predicted.upper_bound
        assert lower is not None and upper is not None
        if lower <= actual.value <= upper:
            continue
        if actual.timestamp in existing:
            continue  # already flagged in a previous sweep
        severity = _severity(actual.value, lower, upper)
        session.add(
            Anomaly(
                organization_id=metric.organization_id,
                metric_id=metric.id,
                detected_at=actual.timestamp,
                actual_value=actual.value,
                expected_value=predicted.predicted_value,
                severity=severity,
                method="residual_threshold",
            )
        )
        worst = max(worst, severity, key=lambda s: order[s])
        created += 1

    if created:
        session.add(
            Notification(
                organization_id=metric.organization_id,
                type="anomaly_detected",
                payload={
                    "metric_id": str(metric.id),
                    "metric_name": metric.name,
                    "count": created,
                    "worst_severity": worst,
                },
            )
        )
        log.info("flagged %d anomalies on metric %s (worst %s)", created, metric.id, worst)
    return created


def detect_anomalies(session: Session) -> int:
    """One sweep over every metric. Returns anomalies created."""
    total = 0
    for metric in session.scalars(select(Metric)).all():
        total += _detect_for_metric(session, metric)
    session.commit()
    return total
