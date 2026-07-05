"""Outbox relay (doc 1 §6.2, guide §5.6).

SELECT unpublished outbox rows FOR UPDATE SKIP LOCKED, publish each to the
EventBus, mark published. SKIP LOCKED means multiple relays can't double-publish
— irrelevant locally (one process) but the code is written for it so production
gets multi-replica safety free.

Kept as a real module even though the POC has no consumers yet: the MVP wires a
real Redis EventBus in here (plan 05 §3 step 7 / §4). Do not delete as "unused".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import OutboxEvent
from shared.providers.event_bus import EventBus

log = logging.getLogger("worker.relay")


def relay_outbox(session: Session, bus: EventBus, batch_size: int = 50) -> int:
    """Publish a batch of unpublished outbox events. Returns the count relayed."""
    events = session.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .order_by(OutboxEvent.created_at)
        .with_for_update(skip_locked=True)
        .limit(batch_size)
    ).all()

    relayed = 0
    for event in events:
        bus.publish(event.event_type, event.payload)
        event.published_at = datetime.now(tz=UTC)
        relayed += 1
    session.commit()
    return relayed
