"""Notifications + dashboard stats — the 'whole product' surface: the bell in
the header and the landing page's at-a-glance numbers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from api.deps import DbDep, PrincipalDep
from api.schemas import DashboardOut, NotificationOut
from shared.db.models import (
    Agent,
    Anomaly,
    Connector,
    DataPoint,
    ForecastRun,
    Metric,
    Notification,
)
from shared.domain import AgentStatus, ConnectorStatus, RunStatus

router = APIRouter(tags=["notifications"])


def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id, type=n.type, payload=n.payload, read_at=n.read_at, created_at=n.created_at
    )


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: DbDep,
    principal: PrincipalDep,
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
) -> list[NotificationOut]:
    stmt = (
        select(Notification)
        .where(Notification.organization_id == uuid.UUID(principal.org_id))
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return [_to_out(n) for n in db.scalars(stmt).all()]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> NotificationOut:
    n = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.organization_id == uuid.UUID(principal.org_id),
        )
    )
    if n is None:
        raise HTTPException(404, "notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(tz=UTC)
    return _to_out(n)


@router.post("/notifications/read-all")
def mark_all_read(db: DbDep, principal: PrincipalDep) -> dict[str, int]:
    from sqlalchemy import update

    result = db.execute(
        update(Notification)
        .where(
            Notification.organization_id == uuid.UUID(principal.org_id),
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(tz=UTC))
    )
    # UPDATE always yields a CursorResult; the generic Result type just can't see it
    return {"marked_read": int(getattr(result, "rowcount", 0) or 0)}


@router.get("/notifications/unread-count")
def unread_count(db: DbDep, principal: PrincipalDep) -> dict[str, int]:
    """A single COUNT(*) for the header bell — polled every 30s, so it must stay
    cheap. Avoids the full /dashboard payload (8 aggregates, incl. an unbounded
    DataPoint count) when all the bell needs is the unread total."""
    n = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.organization_id == uuid.UUID(principal.org_id),
            Notification.read_at.is_(None),
        )
    )
    return {"unread": int(n or 0)}


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: DbDep, principal: PrincipalDep) -> DashboardOut:
    org_id = uuid.UUID(principal.org_id)

    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    day_ago = datetime.now(tz=UTC) - timedelta(hours=24)
    return DashboardOut(
        connectors=count(
            select(func.count()).select_from(Connector).where(Connector.organization_id == org_id)
        ),
        connectors_error=count(
            select(func.count())
            .select_from(Connector)
            .where(Connector.organization_id == org_id, Connector.status == ConnectorStatus.ERROR)
        ),
        metrics=count(
            select(func.count()).select_from(Metric).where(Metric.organization_id == org_id)
        ),
        data_points=count(
            select(func.count()).select_from(DataPoint).where(DataPoint.organization_id == org_id)
        ),
        points_last_24h=count(
            select(func.count())
            .select_from(DataPoint)
            .where(DataPoint.organization_id == org_id, DataPoint.ingested_at >= day_ago)
        ),
        forecast_runs_completed=count(
            select(func.count())
            .select_from(ForecastRun)
            .where(ForecastRun.organization_id == org_id, ForecastRun.status == RunStatus.COMPLETED)
        ),
        agents_active=count(
            select(func.count())
            .select_from(Agent)
            .where(Agent.organization_id == org_id, Agent.status == AgentStatus.ACTIVE)
        ),
        unread_notifications=count(
            select(func.count())
            .select_from(Notification)
            .where(Notification.organization_id == org_id, Notification.read_at.is_(None))
        ),
        open_anomalies=count(
            select(func.count())
            .select_from(Anomaly)
            .where(Anomaly.organization_id == org_id, Anomaly.acknowledged_at.is_(None))
        ),
    )
