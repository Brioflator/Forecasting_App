"""Poller: a seeded connector accumulates data_points with no manual action,
records connector_runs, and the outbox gets an event per point (plan 05 §3 step 7)."""

from __future__ import annotations

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db.models import ConnectorRun, DataPoint, OutboxEvent
from shared.providers.event_bus import InProcessEventBus
from shared.providers.secrets import DotenvSecretsProvider
from shared.settings import Settings
from worker.extractors import GenericRestExtractor, register_extractor
from worker.poller import poll_connector
from worker.relay import relay_outbox


def _settings(tmp_path) -> Settings:
    return Settings(_env_file=None, secret_file=str(tmp_path / "s.env"))  # type: ignore[call-arg]


def _install_mock_extractor(value: float) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": value})

    register_extractor(
        "generic_rest",
        GenericRestExtractor(client=httpx.Client(transport=httpx.MockTransport(handler))),
    )


def test_poll_accumulates_points_and_logs_run(seeded, db_session: Session, tmp_path) -> None:
    _install_mock_extractor(123.0)
    secrets = DotenvSecretsProvider(tmp_path / "s.env")

    ingested = poll_connector(db_session, seeded.connector, secrets, _settings(tmp_path))
    assert ingested == 1

    count = db_session.scalar(
        select(func.count()).select_from(DataPoint).where(DataPoint.metric_id == seeded.metric.id)
    )
    assert count == 1

    run = db_session.scalar(
        select(ConnectorRun).where(ConnectorRun.connector_id == seeded.connector.id)
    )
    assert run is not None
    assert run.status == "succeeded"
    assert run.records_ingested == 1


def test_poll_writes_outbox_and_relay_publishes(seeded, db_session: Session, tmp_path) -> None:
    _install_mock_extractor(5.0)
    secrets = DotenvSecretsProvider(tmp_path / "s.env")
    poll_connector(db_session, seeded.connector, secrets, _settings(tmp_path))

    unpublished = db_session.scalars(
        select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
    ).all()
    assert len(unpublished) == 1
    assert unpublished[0].event_type == "data_point.ingested"

    bus = InProcessEventBus()
    seen: list[dict] = []
    bus.subscribe("data_point.ingested", seen.append)
    relayed = relay_outbox(db_session, bus)
    assert relayed == 1
    assert seen[0]["metric_id"] == str(seeded.metric.id)

    # nothing left unpublished
    assert relay_outbox(db_session, bus) == 0


def test_failing_poll_records_failure(seeded, db_session: Session, tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    register_extractor(
        "generic_rest",
        GenericRestExtractor(client=httpx.Client(transport=httpx.MockTransport(handler))),
    )
    secrets = DotenvSecretsProvider(tmp_path / "s.env")
    ingested = poll_connector(db_session, seeded.connector, secrets, _settings(tmp_path))
    assert ingested == 0

    run = db_session.scalar(
        select(ConnectorRun).where(ConnectorRun.connector_id == seeded.connector.id)
    )
    assert run is not None
    assert run.status == "failed"
    assert run.error_message is not None
