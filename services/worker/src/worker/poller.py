"""Poll one pull connector: fetch the secret, run the extractor, ingest — with
a connector_runs audit row and consecutive-failure tracking (doc 1 §6.1, §7).
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import Connector, Metric, Notification
from shared.models import Point
from shared.providers.secrets import SecretsProvider
from shared.settings import Settings
from worker.extractors import Extractor, get_extractor
from worker.ingest import record_connector_run, upsert_points

log = logging.getLogger("worker.poller")


def _fetch_with_retry(
    extractor: Extractor,
    config: dict,
    secret: str | None,
    cadence: str | None,
    settings: Settings,
) -> list[Point]:
    """Retry transient fetch failures with exponential backoff (MVP ops).
    The last failure propagates so the run is recorded as failed."""
    attempts = max(1, settings.poll_retry_attempts)
    for attempt in range(attempts):
        try:
            return extractor.fetch(config, secret, cadence)
        except Exception:
            if attempt == attempts - 1:
                raise
            delay = settings.poll_retry_backoff_seconds * (2**attempt)
            log.warning(
                "fetch attempt %d/%d failed; retrying in %.1fs", attempt + 1, attempts, delay
            )
            time.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


def poll_connector(
    session: Session,
    connector: Connector,
    secrets: SecretsProvider,
    settings: Settings,
) -> int:
    """Poll a connector's metrics once. Returns total points ingested. Errors are
    recorded (never raised out) so the scheduler keeps running."""
    metrics = session.scalars(select(Metric).where(Metric.connector_id == connector.id)).all()
    if not metrics:
        return 0

    secret: str | None = None
    if connector.secret_ref:
        try:
            secret = secrets.get_secret(str(connector.organization_id), connector.secret_ref)
        except Exception:  # noqa: BLE001 — missing secret is a run failure, not a crash
            secret = None

    extractor = get_extractor(connector.definition.key)
    total = 0
    try:
        for metric in metrics:
            config = {**connector.config, **metric.extraction_config}
            points = _fetch_with_retry(extractor, config, secret, connector.schedule_cron, settings)
            total += upsert_points(session, metric, points, source="poll")
        record_connector_run(
            session,
            connector.id,
            connector.organization_id,
            status="succeeded",
            records_ingested=total,
        )
        if connector.status == "error":
            connector.status = "active"  # a good poll clears the error state
        session.commit()
        return total
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        record_connector_run(
            session,
            connector.id,
            connector.organization_id,
            status="failed",
            error_message=str(exc),
        )
        _maybe_flip_to_error(session, connector, settings)
        session.commit()
        log.warning("poll failed for connector %s: %s", connector.id, exc)
        return 0


def _maybe_flip_to_error(session: Session, connector: Connector, settings: Settings) -> None:
    """After N consecutive failed runs, flip the connector to 'error' (doc 1 §7)."""
    from shared.db.models import ConnectorRun

    recent = session.scalars(
        select(ConnectorRun)
        .where(ConnectorRun.connector_id == connector.id)
        .order_by(ConnectorRun.started_at.desc())
        .limit(settings.max_consecutive_failures)
    ).all()
    if len(recent) >= settings.max_consecutive_failures and all(
        r.status == "failed" for r in recent
    ):
        if connector.status != "error":
            # Raise the notification once, on the transition (doc 1 §7).
            session.add(
                Notification(
                    organization_id=connector.organization_id,
                    type="connector_error",
                    payload={
                        "connector_id": str(connector.id),
                        "connector_name": connector.name,
                        "consecutive_failures": settings.max_consecutive_failures,
                    },
                )
            )
        connector.status = "error"
