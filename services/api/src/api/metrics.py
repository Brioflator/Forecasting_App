"""Metric CRUD, series retrieval, and forecast enqueue (doc 1 §5.2, §5.4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from api.deps import DbDep, PrincipalDep
from api.schemas import (
    DataPointOut,
    ForecastCreate,
    ForecastRunOut,
    MetricCreate,
    MetricDataOut,
    MetricListItemOut,
    MetricOut,
)
from shared.db.models import Connector, DataPoint, ForecastRun, Metric

router = APIRouter(tags=["metrics"])


def _metric_out(m: Metric) -> MetricOut:
    return MetricOut(
        id=m.id,
        connector_id=m.connector_id,
        name=m.name,
        key=m.key,
        unit=m.unit,
        seasonal_period=m.seasonal_period,
    )


def _owned_connector(db: DbDep, org_id: str, connector_id: uuid.UUID) -> Connector:
    connector = db.scalar(
        select(Connector).where(
            Connector.id == connector_id, Connector.organization_id == uuid.UUID(org_id)
        )
    )
    if connector is None:
        raise HTTPException(404, "connector not found")
    return connector


def _owned_metric(db: DbDep, org_id: str, metric_id: uuid.UUID) -> Metric:
    metric = db.scalar(
        select(Metric).where(Metric.id == metric_id, Metric.organization_id == uuid.UUID(org_id))
    )
    if metric is None:
        raise HTTPException(404, "metric not found")
    return metric


@router.post("/connectors/{connector_id}/metrics", response_model=MetricOut, status_code=201)
def create_metric(
    connector_id: uuid.UUID, body: MetricCreate, db: DbDep, principal: PrincipalDep
) -> MetricOut:
    connector = _owned_connector(db, principal.org_id, connector_id)
    if db.scalar(select(Metric).where(Metric.connector_id == connector.id, Metric.key == body.key)):
        raise HTTPException(409, f"metric key already exists on this connector: {body.key}")
    metric = Metric(
        organization_id=uuid.UUID(principal.org_id),
        connector_id=connector.id,
        name=body.name,
        key=body.key,
        unit=body.unit,
        seasonal_period=body.seasonal_period,
        extraction_config=body.extraction_config,
    )
    db.add(metric)
    db.flush()
    return _metric_out(metric)


@router.get("/connectors/{connector_id}/metrics", response_model=list[MetricOut])
def list_metrics(connector_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> list[MetricOut]:
    _owned_connector(db, principal.org_id, connector_id)
    rows = db.scalars(
        select(Metric).where(Metric.connector_id == connector_id).order_by(Metric.created_at)
    ).all()
    return [_metric_out(m) for m in rows]


@router.get("/metrics", response_model=list[MetricListItemOut])
def list_all_metrics(db: DbDep, principal: PrincipalDep) -> list[MetricListItemOut]:
    """Org-wide dataset list with sparklines (doc 4 §3)."""
    metrics = db.scalars(
        select(Metric)
        .where(Metric.organization_id == uuid.UUID(principal.org_id))
        .order_by(Metric.created_at)
    ).all()
    out: list[MetricListItemOut] = []
    for m in metrics:
        recent = list(
            db.scalars(
                select(DataPoint)
                .where(DataPoint.metric_id == m.id)
                .order_by(DataPoint.timestamp.desc())
                .limit(30)
            ).all()
        )
        recent.reverse()
        out.append(
            MetricListItemOut(
                **_metric_out(m).model_dump(),
                connector_name=m.connector.name,
                n_points=db.scalar(
                    select(func.count()).select_from(DataPoint).where(DataPoint.metric_id == m.id)
                )
                or 0,
                last_updated=recent[-1].timestamp if recent else None,
                spark=[r.value for r in recent],
            )
        )
    return out


@router.get("/metrics/{metric_id}", response_model=MetricOut)
def get_metric(metric_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> MetricOut:
    return _metric_out(_owned_metric(db, principal.org_id, metric_id))


@router.get("/metrics/{metric_id}/data", response_model=MetricDataOut)
def get_metric_data(
    metric_id: uuid.UUID,
    db: DbDep,
    principal: PrincipalDep,
    limit: int = Query(1000, ge=1, le=10000),
) -> MetricDataOut:
    metric = _owned_metric(db, principal.org_id, metric_id)
    rows = db.scalars(
        select(DataPoint)
        .where(DataPoint.metric_id == metric.id)
        .order_by(DataPoint.timestamp)
        .limit(limit)
    ).all()
    return MetricDataOut(
        metric_id=metric.id,
        points=[DataPointOut(timestamp=r.timestamp, value=r.value, source=r.source) for r in rows],
    )


@router.post("/metrics/{metric_id}/forecast", response_model=ForecastRunOut, status_code=202)
def enqueue_forecast(
    metric_id: uuid.UUID, body: ForecastCreate, db: DbDep, principal: PrincipalDep
) -> ForecastRunOut:
    """Insert a pending forecast_runs row — the row IS the job (doc 1 §5.4).
    `worker` polls pending rows, calls `ml`, and writes the result back."""
    metric = _owned_metric(db, principal.org_id, metric_id)
    if body.horizon < 1:
        raise HTTPException(422, "horizon must be >= 1")
    if body.model not in ("auto", "sarima", "ets", "prophet"):
        raise HTTPException(422, "unknown model")
    run = ForecastRun(
        organization_id=uuid.UUID(principal.org_id),
        metric_id=metric.id,
        model_type=body.model,
        horizon=body.horizon,
        status="pending",
    )
    db.add(run)
    db.flush()
    return _run_to_out(run)


def _run_to_out(run: ForecastRun) -> ForecastRunOut:
    from api.forecasts import run_to_out

    return run_to_out(run)
