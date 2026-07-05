"""Operational basics (plan 05 §4): retry/backoff, error notifications,
agent staleness, partition maintenance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shared.db.models import Agent, Notification
from shared.providers.secrets import DotenvSecretsProvider
from shared.settings import Settings
from worker.extractors import GenericRestExtractor, register_extractor
from worker.maintenance import ensure_partitions, mark_stale_agents
from worker.poller import poll_connector


def _settings(tmp_path, **overrides: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        secret_file=str(tmp_path / "s.env"),
        poll_retry_backoff_seconds=0.01,  # keep tests fast
        **overrides,
    )


class FlakyTransport(httpx.BaseTransport):
    """Fails N times, then succeeds — exercises the retry path."""

    def __init__(self, failures: int, value: float = 7.0):
        self.failures = failures
        self.calls = 0
        self.value = value

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls <= self.failures:
            return httpx.Response(503, json={"error": "try later"})
        return httpx.Response(200, json={"value": self.value})


def test_transient_failure_recovers_via_retry(seeded, db_session: Session, tmp_path) -> None:
    transport = FlakyTransport(failures=2)
    register_extractor(
        "generic_rest", GenericRestExtractor(client=httpx.Client(transport=transport))
    )
    settings = _settings(tmp_path, poll_retry_attempts=3)

    ingested = poll_connector(
        db_session, seeded.connector, DotenvSecretsProvider(tmp_path / "s.env"), settings
    )
    assert ingested == 1  # third attempt succeeded
    assert transport.calls == 3


def test_connector_flips_to_error_with_notification(seeded, db_session: Session, tmp_path) -> None:
    register_extractor(
        "generic_rest",
        GenericRestExtractor(
            client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
        ),
    )
    settings = _settings(tmp_path, poll_retry_attempts=1, max_consecutive_failures=3)
    secrets = DotenvSecretsProvider(tmp_path / "s.env")

    for _ in range(3):
        poll_connector(db_session, seeded.connector, secrets, settings)

    db_session.refresh(seeded.connector)
    assert seeded.connector.status == "error"

    notes = db_session.scalars(
        select(Notification).where(Notification.type == "connector_error")
    ).all()
    assert len(notes) == 1  # raised once, on the transition
    assert notes[0].payload["connector_id"] == str(seeded.connector.id)


def test_mark_stale_agents(seeded, db_session: Session, tmp_path) -> None:
    fresh = Agent(
        organization_id=seeded.org_id,
        connector_id=seeded.connector.id,
        ingestion_token_hash="h1",
        last_heartbeat_at=datetime.now(tz=UTC),
    )
    old = Agent(
        organization_id=seeded.org_id,
        connector_id=seeded.connector.id,
        ingestion_token_hash="h2",
        last_heartbeat_at=datetime.now(tz=UTC) - timedelta(minutes=30),
    )
    db_session.add_all([fresh, old])
    db_session.commit()

    flipped = mark_stale_agents(db_session, _settings(tmp_path, agent_stale_after_minutes=5))
    assert flipped == 1
    db_session.refresh(old)
    db_session.refresh(fresh)
    assert old.status == "stale"
    assert fresh.status == "active"
    note = db_session.scalar(select(Notification).where(Notification.type == "agent_unreachable"))
    assert note is not None and note.payload["agent_id"] == str(old.id)


def test_ensure_partitions_creates_future_months(seeded, db_session: Session) -> None:
    ensure_partitions(db_session, months_ahead=5)
    # the +5 month partition must now exist for every partitioned table
    from datetime import date

    future = date.today().replace(day=1)
    for _ in range(5):
        future = (future + timedelta(days=32)).replace(day=1)
    suffix = future.strftime("%Y_%m")
    for table in ("data_points", "connector_runs", "audit_log"):
        exists = db_session.execute(
            text("SELECT 1 FROM pg_class WHERE relname = :n"), {"n": f"{table}_{suffix}"}
        ).scalar()
        assert exists == 1, f"missing partition {table}_{suffix}"
