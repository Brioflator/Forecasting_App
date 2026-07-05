"""Worker-side ingestion helpers.

The upsert+outbox path itself lives in shared.db.ingest (one code path for
pull/push/agent, doc 1 §3); this module re-exports it for the poller and owns
the connector_runs audit row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from shared.db.ingest import upsert_points
from shared.db.models import ConnectorRun

__all__ = ["record_connector_run", "upsert_points"]


def record_connector_run(
    session: Session,
    connector_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    status: str,
    records_ingested: int = 0,
    error_message: str | None = None,
) -> ConnectorRun:
    run = ConnectorRun(
        connector_id=connector_id,
        organization_id=organization_id,
        started_at=datetime.now(tz=UTC),
        finished_at=datetime.now(tz=UTC),
        status=status,
        records_ingested=records_ingested,
        error_message=error_message,
    )
    session.add(run)
    return run
