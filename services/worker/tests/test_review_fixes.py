"""Regression tests for the code-review criticals.

C1 — sync_pull_jobs picks up runtime-created connectors (no worker restart).
C2 — transport-level ml failures back off and terminally fail, never hot-loop.
C3 — duplicate timestamps within one payload upsert cleanly (last write wins).
C4 — the Redis consumer loop survives handler and broker errors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db.models import Connector, DataPoint, ForecastRun
from shared.models import ForecastRequest, Point
from shared.settings import Settings
from worker.dispatch import (
    ATTEMPTS_KEY,
    NEXT_ATTEMPT_KEY,
    dispatch_pending_forecasts,
)
from worker.ingest import upsert_points


def _settings(**overrides: object) -> Settings:
    overrides.setdefault("forecast_dispatch_backoff_seconds", 0.05)
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


# ── C3: payload-internal duplicate timestamps ─────────────────────────────


def test_duplicate_timestamps_in_one_payload_upsert_cleanly(seeded, db_session: Session) -> None:
    ts = datetime(2026, 7, 1, tzinfo=UTC)
    points = [
        Point(timestamp=ts, value=1.0),
        Point(timestamp=ts + timedelta(minutes=1), value=2.0),
        Point(timestamp=ts, value=3.0),  # duplicate — would raise "cannot affect row a second time"
    ]
    written = upsert_points(db_session, seeded.metric, points, source="webhook")
    db_session.flush()
    assert written == 2  # deduped
    rows = db_session.scalars(
        select(DataPoint)
        .where(DataPoint.metric_id == seeded.metric.id)
        .order_by(DataPoint.timestamp)
    ).all()
    assert [r.value for r in rows] == [3.0, 2.0]  # last write wins


# ── C2: dispatch transport failures ───────────────────────────────────────


class _DownMlClient:
    def __init__(self) -> None:
        self.calls = 0

    def forecast(self, request: ForecastRequest) -> dict:
        self.calls += 1
        raise httpx.ConnectError("connection refused")


def _enqueue(db_session: Session, seeded) -> uuid.UUID:
    run = ForecastRun(
        organization_id=seeded.org_id,
        metric_id=seeded.metric.id,
        model_type="auto",
        horizon=3,
        status="pending",
    )
    db_session.add(run)
    db_session.commit()
    return run.id


def test_transport_failure_backs_off_instead_of_hot_looping(seeded, db_session: Session) -> None:
    run_id = _enqueue(db_session, seeded)
    client = _DownMlClient()
    settings = _settings(forecast_dispatch_max_attempts=5, forecast_dispatch_backoff_seconds=60)

    dispatch_pending_forecasts(db_session, client, settings=settings)
    run = db_session.get(ForecastRun, run_id)
    assert run is not None
    assert run.status == "pending"  # requeued, not stuck in running
    assert run.model_params[ATTEMPTS_KEY] == 1
    assert run.model_params[NEXT_ATTEMPT_KEY] is not None

    # A second sweep inside the backoff window must NOT call ml again.
    dispatch_pending_forecasts(db_session, client, settings=settings)
    assert client.calls == 1
    run = db_session.get(ForecastRun, run_id)
    assert run is not None and run.model_params[ATTEMPTS_KEY] == 1


def test_transport_failure_fails_terminally_at_cap(seeded, db_session: Session) -> None:
    run_id = _enqueue(db_session, seeded)
    client = _DownMlClient()
    settings = _settings(forecast_dispatch_max_attempts=3, forecast_dispatch_backoff_seconds=0.0)

    for _ in range(3):
        dispatch_pending_forecasts(db_session, client, settings=settings)

    run = db_session.get(ForecastRun, run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error_message is not None and "3 attempts" in run.error_message
    assert client.calls == 3

    # terminal: further sweeps never touch it again
    dispatch_pending_forecasts(db_session, client, settings=settings)
    assert client.calls == 3


# ── C1: runtime connector sync ────────────────────────────────────────────


def test_sync_pull_jobs_tracks_runtime_connectors(seeded, db_session: Session, tmp_path) -> None:
    from apscheduler.schedulers.background import BackgroundScheduler

    from shared.providers.secrets import DotenvSecretsProvider
    from worker.main import sync_pull_jobs

    db_url = db_session.get_bind().engine.url.render_as_string(hide_password=False)
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url=db_url,
        secret_file=str(tmp_path / "s.env"),
    )
    from shared.db import session as session_mod

    session_mod.reset_engine()  # bind the factory sync_pull_jobs uses to the test DB

    secrets = DotenvSecretsProvider(tmp_path / "s.env")
    scheduler = BackgroundScheduler()

    added, removed = sync_pull_jobs(scheduler, settings, secrets)
    assert added == 1  # the seeded pull connector
    assert scheduler.get_job(f"poll-{seeded.connector.id}") is not None

    # A connector created AFTER startup gets picked up by the next sync.
    late = Connector(
        organization_id=seeded.org_id,
        connector_definition_id=seeded.connector.connector_definition_id,
        name="created after startup",
        ingestion_method="pull",
        schedule_cron="*/5 * * * *",
    )
    db_session.add(late)
    db_session.commit()

    added, removed = sync_pull_jobs(scheduler, settings, secrets)
    assert added == 1 and removed == 0
    assert scheduler.get_job(f"poll-{late.id}") is not None

    # Pausing removes its job on the next sync.
    late.status = "paused"
    db_session.commit()
    added, removed = sync_pull_jobs(scheduler, settings, secrets)
    assert removed == 1
    assert scheduler.get_job(f"poll-{late.id}") is None
    # scheduler was never started — nothing to shut down


# ── C4: redis consumer resilience ─────────────────────────────────────────


class _FlakyRedis:
    """xreadgroup fails once, then delivers one message, then returns empty."""

    def __init__(self) -> None:
        self.reads = 0
        self.acked: list[str] = []

    def xgroup_create(self, *a, **k) -> None:
        pass

    def xreadgroup(self, *a, **k):
        self.reads += 1
        if self.reads == 1:
            raise ConnectionError("redis hiccup")
        if self.reads == 2:
            return [("topic", [("1-1", {"payload": '{"metric_id": "m1"}'})])]
        return []

    def xack(self, topic, group, msg_id) -> None:
        self.acked.append(msg_id)


def test_redis_consumer_survives_broker_error() -> None:
    import time

    from shared.providers.event_bus import RedisEventBus

    bus = RedisEventBus("redis://unused", block_ms=10)
    fake = _FlakyRedis()
    bus._client = fake  # inject; _redis() returns it without connecting

    seen: list[dict] = []
    bus.subscribe("topic", seen.append)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not seen:
        time.sleep(0.05)
    bus.close()

    # the first read raised — the thread must have survived it and delivered
    assert seen == [{"metric_id": "m1"}]
    assert fake.acked == ["1-1"]
    assert fake.reads >= 2


def test_redis_consumer_acks_even_when_handler_raises() -> None:
    import time

    from shared.providers.event_bus import RedisEventBus

    bus = RedisEventBus("redis://unused", block_ms=10)
    fake = _FlakyRedis()
    fake.reads = 1  # skip the hiccup; next read delivers
    bus._client = fake

    def bad_handler(payload: dict) -> None:
        raise RuntimeError("handler bug")

    bus.subscribe("topic", bad_handler)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not fake.acked:
        time.sleep(0.05)
    bus.close()

    assert fake.acked == ["1-1"]  # acked despite the handler crash (at-least-once)


# sanity: counts stay consistent through the dedupe path
def test_upsert_returns_written_count(seeded, db_session: Session) -> None:
    ts = datetime(2026, 7, 2, tzinfo=UTC)
    n = upsert_points(db_session, seeded.metric, [Point(timestamp=ts, value=1.0)], source="poll")
    db_session.flush()
    assert n == 1
    total = db_session.scalar(select(func.count()).select_from(DataPoint))
    assert total == 1


@pytest.fixture(autouse=True)
def _restore_engine():
    """test_sync_pull_jobs rebinds the shared engine; restore it afterwards."""
    yield
    from shared.db import session as session_mod

    session_mod.reset_engine()
