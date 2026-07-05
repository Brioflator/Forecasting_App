"""Metric CRUD, series retrieval, and forecast enqueue (doc 1 §5.2, §5.4)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from api.deps import DbDep, PrincipalDep
from api.schemas import (
    AnomalyOut,
    DataPointOut,
    ForecastCreate,
    ForecastRunOut,
    ForecastRunSummaryOut,
    MetricCreate,
    MetricDataOut,
    MetricListItemOut,
    MetricOut,
    MetricUpdate,
)
from api.serializers import run_to_out
from shared.db.models import Anomaly, Connector, DataPoint, ForecastRun, Metric

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
    org_id = uuid.UUID(principal.org_id)
    metrics = db.scalars(
        select(Metric)
        .where(Metric.organization_id == org_id)
        .options(selectinload(Metric.connector))
        .order_by(Metric.created_at)
    ).all()

    # One grouped count + one windowed sparkline query for the whole org,
    # instead of two queries per metric (N+1 at "hundreds of metrics" scale).
    counts: dict[uuid.UUID, int] = {
        row[0]: row[1]
        for row in db.execute(
            select(DataPoint.metric_id, func.count())
            .where(DataPoint.organization_id == org_id)
            .group_by(DataPoint.metric_id)
        ).all()
    }
    ranked = (
        select(
            DataPoint.metric_id,
            DataPoint.timestamp,
            DataPoint.value,
            func.row_number()
            .over(partition_by=DataPoint.metric_id, order_by=DataPoint.timestamp.desc())
            .label("rn"),
        )
        .where(DataPoint.organization_id == org_id)
        .subquery()
    )
    spark_rows = db.execute(
        select(ranked.c.metric_id, ranked.c.timestamp, ranked.c.value)
        .where(ranked.c.rn <= 30)
        .order_by(ranked.c.metric_id, ranked.c.timestamp)
    ).all()
    sparks: dict[uuid.UUID, list[tuple]] = {}
    for metric_id, ts, value in spark_rows:
        sparks.setdefault(metric_id, []).append((ts, value))

    out: list[MetricListItemOut] = []
    for m in metrics:
        recent = sparks.get(m.id, [])
        out.append(
            MetricListItemOut(
                **_metric_out(m).model_dump(),
                connector_name=m.connector.name,
                n_points=counts.get(m.id, 0),
                last_updated=recent[-1][0] if recent else None,
                spark=[v for _, v in recent],
            )
        )
    return out


@router.get("/metrics/{metric_id}", response_model=MetricOut)
def get_metric(metric_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> MetricOut:
    return _metric_out(_owned_metric(db, principal.org_id, metric_id))


@router.patch("/metrics/{metric_id}", response_model=MetricOut)
def update_metric(
    metric_id: uuid.UUID, body: MetricUpdate, db: DbDep, principal: PrincipalDep
) -> MetricOut:
    metric = _owned_metric(db, principal.org_id, metric_id)
    if body.name is not None:
        metric.name = body.name
    if body.unit is not None:
        metric.unit = body.unit
    if body.seasonal_period is not None:
        # 0 clears it back to auto-detect (PATCH can't send null distinguishably here)
        metric.seasonal_period = body.seasonal_period or None
    db.flush()
    return _metric_out(metric)


@router.delete("/metrics/{metric_id}", status_code=204)
def delete_metric(metric_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> None:
    metric = _owned_metric(db, principal.org_id, metric_id)
    db.delete(metric)  # data_points/forecast_runs/eda_reports cascade via FK


@router.get("/metrics/{metric_id}/forecasts", response_model=list[ForecastRunSummaryOut])
def list_metric_forecasts(
    metric_id: uuid.UUID,
    db: DbDep,
    principal: PrincipalDep,
    limit: int = Query(10, ge=1, le=50),
) -> list[ForecastRunSummaryOut]:
    """Forecast history, newest first — lets the UI reload the latest result."""
    metric = _owned_metric(db, principal.org_id, metric_id)
    runs = db.scalars(
        select(ForecastRun)
        .where(ForecastRun.metric_id == metric.id)
        # id tiebreaker: rows created in one transaction share now()
        .order_by(ForecastRun.requested_at.desc(), ForecastRun.id.desc())
        .limit(limit)
    ).all()
    out = []
    for run in runs:
        params = run.model_params if isinstance(run.model_params, dict) else {}
        out.append(
            ForecastRunSummaryOut(
                id=run.id,
                metric_id=run.metric_id,
                model_type=run.model_type,
                resolved_model=params.get("resolved_model"),
                horizon=run.horizon,
                status=run.status,
                requested_at=run.requested_at,
                completed_at=run.completed_at,
                warning=params.get("warning"),
                error_message=run.error_message,
            )
        )
    return out


@router.get("/metrics/{metric_id}/anomalies", response_model=list[AnomalyOut])
def list_metric_anomalies(
    metric_id: uuid.UUID,
    db: DbDep,
    principal: PrincipalDep,
    limit: int = Query(50, ge=1, le=200),
) -> list[AnomalyOut]:
    metric = _owned_metric(db, principal.org_id, metric_id)
    rows = db.scalars(
        select(Anomaly)
        .where(Anomaly.metric_id == metric.id)
        .order_by(Anomaly.detected_at.desc())
        .limit(limit)
    ).all()
    return [
        AnomalyOut(
            id=a.id,
            metric_id=a.metric_id,
            detected_at=a.detected_at,
            actual_value=a.actual_value,
            expected_value=a.expected_value,
            severity=a.severity,
            method=a.method,
            acknowledged_at=a.acknowledged_at,
        )
        for a in rows
    ]


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
    return run_to_out(run)
