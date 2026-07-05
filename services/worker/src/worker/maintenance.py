"""Scheduled maintenance (MVP operational basics).

- ensure_partitions: keeps monthly partitions created ahead of time (migration
  0006's ensure_month_partitions; pg_partman takes this over on Supabase).
- mark_stale_agents: flips agents whose heartbeat is too old to 'stale' and
  raises an agent_unreachable notification once per transition (guide §7.7).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shared.db.models import Agent, Notification
from shared.settings import Settings

log = logging.getLogger("worker.maintenance")

PARTITIONED_TABLES = ("data_points", "connector_runs", "audit_log")


def ensure_partitions(session: Session, months_ahead: int = 3) -> None:
    for table in PARTITIONED_TABLES:
        session.execute(
            text("SELECT ensure_month_partitions(:parent, :ahead)"),
            {"parent": table, "ahead": months_ahead},
        )
    session.commit()
    log.info("partition maintenance ran for %s", ", ".join(PARTITIONED_TABLES))


def mark_stale_agents(session: Session, settings: Settings) -> int:
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=settings.agent_stale_after_minutes)
    stale = session.scalars(
        select(Agent).where(
            Agent.status == "active",
            Agent.last_heartbeat_at.is_not(None),
            Agent.last_heartbeat_at < cutoff,
        )
    ).all()
    for agent in stale:
        agent.status = "stale"
        session.add(
            Notification(
                organization_id=agent.organization_id,
                type="agent_unreachable",
                payload={
                    "agent_id": str(agent.id),
                    "last_heartbeat_at": agent.last_heartbeat_at.isoformat()
                    if agent.last_heartbeat_at
                    else None,
                },
            )
        )
    session.commit()
    return len(stale)
