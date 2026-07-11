"""EDA surfaced through the api (plan 05 §4): api → ml /eda over HTTP, results
persisted in eda_reports, plain-language readings passed through untouched.

This is the one place `api` talks to `ml` directly — EDA is a fast, synchronous
computation (no model fitting), so routing it through the worker's job queue
would add latency for nothing. Forecasts stay on the worker path.
"""

from __future__ import annotations

from functools import lru_cache

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import DbDep, OwnedMetricDep
from api.schemas import EdaReportOut
from shared.db.models import DataPoint, EdaReportRow
from shared.settings import get_settings

router = APIRouter(tags=["eda"])


class EdaClient:
    """Thin HTTP client to ml /eda; tests override via set_eda_client()."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def eda(self, series: list[dict], seasonal_period: int | None) -> dict:
        resp = httpx.post(
            f"{self._base_url}/eda",
            json={"series": series, "seasonal_period": seasonal_period},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()


@lru_cache
def _default_client() -> EdaClient:
    return EdaClient(get_settings().ml_service_url)


_override: EdaClient | None = None


def set_eda_client(client: EdaClient | None) -> None:
    global _override
    _override = client


def _client() -> EdaClient:
    return _override or _default_client()


def _to_out(report: EdaReportRow) -> EdaReportOut:
    return EdaReportOut(
        id=report.id,
        metric_id=report.metric_id,
        generated_at=report.generated_at,
        stationarity=report.stationarity or {},
        seasonality=report.seasonality or {},
        acf_pacf=report.acf_pacf or {},
    )


@router.post("/metrics/{metric_id}/eda", response_model=EdaReportOut)
def generate_eda(metric: OwnedMetricDep, db: DbDep) -> EdaReportOut:
    rows = db.scalars(
        select(DataPoint).where(DataPoint.metric_id == metric.id).order_by(DataPoint.timestamp)
    ).all()
    if len(rows) < 4:
        raise HTTPException(422, f"not enough data for EDA (have {len(rows)}, need 4)")

    series = [{"timestamp": r.timestamp.isoformat(), "value": r.value} for r in rows]
    try:
        result = _client().eda(series, metric.seasonal_period)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"ml service unavailable: {exc}") from exc

    report = EdaReportRow(
        organization_id=metric.organization_id,
        metric_id=metric.id,
        stationarity=result.get("stationarity"),
        seasonality=result.get("seasonality"),
        acf_pacf=result.get("acf_pacf"),
    )
    db.add(report)
    db.flush()
    return _to_out(report)


@router.get("/metrics/{metric_id}/eda", response_model=EdaReportOut)
def latest_eda(metric: OwnedMetricDep, db: DbDep) -> EdaReportOut:
    report = db.scalar(
        select(EdaReportRow)
        .where(EdaReportRow.metric_id == metric.id)
        .order_by(EdaReportRow.generated_at.desc())
        .limit(1)
    )
    if report is None:
        raise HTTPException(404, "no EDA report yet — POST to generate one")
    return _to_out(report)
