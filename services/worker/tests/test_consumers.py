"""auto-forecast-on-ingest consumer: throttled, idempotent, bus-driven."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db.models import ForecastRun
from shared.providers.event_bus import InProcessEventBus
from shared.settings import Settings
from worker.consumers import maybe_enqueue_auto_forecast
from worker.ingest import upsert_points
from worker.relay import relay_outbox


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def _payload(seeded) -> dict:
    return {"metric_id": str(seeded.metric.id), "organization_id": str(seeded.org_id)}


def test_enqueues_once_then_throttles(seeded, db_session: Session) -> None:
    settings = _settings(auto_forecast_min_interval_minutes=15)
    assert maybe_enqueue_auto_forecast(db_session, _payload(seeded), settings) is True
    db_session.commit()
    # redelivered / next-point event inside the window → no-op (idempotent)
    assert maybe_enqueue_auto_forecast(db_session, _payload(seeded), settings) is False

    count = db_session.scalar(select(func.count()).select_from(ForecastRun))
    assert count == 1
    run = db_session.scalar(select(ForecastRun))
    assert run is not None
    assert run.status == "pending"
    assert run.model_type == "auto"


def test_disabled_when_interval_zero(seeded, db_session: Session) -> None:
    settings = _settings(auto_forecast_min_interval_minutes=0)
    assert maybe_enqueue_auto_forecast(db_session, _payload(seeded), settings) is False


def test_unknown_metric_is_noop(seeded, db_session: Session) -> None:
    settings = _settings(auto_forecast_min_interval_minutes=15)
    payload = {"metric_id": "00000000-0000-0000-0000-00000000dead"}
    assert maybe_enqueue_auto_forecast(db_session, payload, settings) is False


def test_full_path_ingest_to_enqueued_run_via_bus(seeded, db_session: Session) -> None:
    """The real chain: upsert → outbox → relay → bus → consumer → pending run."""
    from datetime import UTC, datetime

    from shared.models import Point

    settings = _settings(auto_forecast_min_interval_minutes=15)
    bus = InProcessEventBus()

    def _consumer(payload: dict) -> None:
        if maybe_enqueue_auto_forecast(db_session, payload, settings):
            db_session.commit()

    bus.subscribe("data_point.ingested", _consumer)

    upsert_points(
        db_session,
        seeded.metric,
        [Point(timestamp=datetime(2026, 7, 1, tzinfo=UTC), value=1.0)],
        source="poll",
    )
    db_session.commit()
    relayed = relay_outbox(db_session, bus)
    assert relayed == 1

    run = db_session.scalar(select(ForecastRun).where(ForecastRun.metric_id == seeded.metric.id))
    assert run is not None and run.status == "pending"
