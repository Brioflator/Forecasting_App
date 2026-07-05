"""EventBus consumers (plan 05 §4 "real event path").

auto-forecast-on-ingest: when data_point.ingested fires, enqueue a forecast run
for that metric — throttled to at most one per AUTO_FORECAST_MIN_INTERVAL_MINUTES
per metric, and never while one is already pending/running. Consumers must be
idempotent (at-least-once delivery, doc 1 §7): the throttle check makes a
redelivered event a no-op.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from shared.db.models import ForecastRun, Metric
from shared.providers.event_bus import EventBus
from shared.settings import Settings

log = logging.getLogger("worker.consumers")


def maybe_enqueue_auto_forecast(session: Session, payload: dict, settings: Settings) -> bool:
    """Returns True if a run was enqueued."""
    if settings.auto_forecast_min_interval_minutes <= 0:
        return False
    try:
        metric_id = uuid.UUID(payload["metric_id"])
    except (KeyError, ValueError):
        return False

    cutoff = datetime.now(tz=UTC) - timedelta(minutes=settings.auto_forecast_min_interval_minutes)
    blocking = session.scalar(
        select(ForecastRun.id)
        .where(
            ForecastRun.metric_id == metric_id,
            or_(
                ForecastRun.status.in_(("pending", "running")),
                ForecastRun.requested_at > cutoff,
            ),
        )
        .limit(1)
    )
    if blocking is not None:
        return False

    metric = session.get(Metric, metric_id)
    if metric is None:
        return False

    session.add(
        ForecastRun(
            organization_id=metric.organization_id,
            metric_id=metric.id,
            model_type="auto",
            horizon=settings.auto_forecast_horizon,
            status="pending",
        )
    )
    log.info("auto-forecast enqueued for metric %s", metric_id)
    return True


def register_consumers(
    bus: EventBus, session_factory: sessionmaker[Session], settings: Settings
) -> None:
    def _on_ingested(payload: dict) -> None:
        try:
            with session_factory() as session:
                if maybe_enqueue_auto_forecast(session, payload, settings):
                    session.commit()
        except Exception:  # noqa: BLE001 — a consumer crash must not kill the bus thread
            log.exception("auto-forecast consumer failed")

    bus.subscribe("data_point.ingested", _on_ingested)
