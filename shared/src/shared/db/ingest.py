"""The single normalize→upsert→outbox ingestion path (doc 1 §3).

Pull (worker poller), push (api webhook ingress), and agent (/ingest) all
converge here, so nothing downstream knows or cares which route delivered the
data. The (metric_id, timestamp) upsert makes every route idempotent, and the
outbox row rides the same transaction as the business write (guide §5.6).
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.db.models import DataPoint, Metric, OutboxEvent
from shared.models import Point


def upsert_points(session: Session, metric: Metric, points: list[Point], source: str) -> int:
    """Upsert points and enqueue one outbox event per point. Returns the number
    of points written (inserted or updated)."""
    if not points:
        return 0
    # Dedupe within the payload (last write wins): a multi-row ON CONFLICT DO
    # UPDATE that hits the same (metric_id, timestamp) twice in ONE statement
    # raises "cannot affect row a second time" — and push sources do send
    # duplicate timestamps in a single delivery.
    points = list({p.timestamp: p for p in points}.values())
    rows = [
        {
            "metric_id": metric.id,
            "organization_id": metric.organization_id,
            "timestamp": p.timestamp,
            "value": p.value,
            "source": source,
        }
        for p in points
    ]
    stmt = pg_insert(DataPoint).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[DataPoint.metric_id, DataPoint.timestamp],
        set_={"value": stmt.excluded.value, "source": stmt.excluded.source},
    )
    session.execute(stmt)

    for p in points:
        session.add(
            OutboxEvent(
                aggregate_type="data_point",
                aggregate_id=str(metric.id),
                event_type="data_point.ingested",
                payload={
                    "metric_id": str(metric.id),
                    "organization_id": str(metric.organization_id),
                    "timestamp": p.timestamp.isoformat(),
                    "value": p.value,
                    "source": source,
                },
            )
        )
    return len(points)
