"""Forecast retrieval + CSV export (doc 1 §5.2, guide §6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from api.deps import BlobDep, DbDep, PrincipalDep
from api.export import CONTENT_TYPES, create_export
from api.schemas import ForecastRunOut
from api.serializers import run_to_out
from shared.db.models import ExportJob, ForecastRun

router = APIRouter(tags=["forecasts"])


def _owned_run(db: DbDep, org_id: str, forecast_id: uuid.UUID) -> ForecastRun:
    run = db.scalar(
        select(ForecastRun).where(
            ForecastRun.id == forecast_id,
            ForecastRun.organization_id == uuid.UUID(org_id),
        )
    )
    if run is None:
        raise HTTPException(404, "forecast not found")
    return run


@router.get("/forecasts/{forecast_id}", response_model=ForecastRunOut)
def get_forecast(forecast_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> ForecastRunOut:
    return run_to_out(_owned_run(db, principal.org_id, forecast_id))


@router.get("/forecasts/{forecast_id}/export")
def export_forecast(
    forecast_id: uuid.UUID,
    db: DbDep,
    principal: PrincipalDep,
    blob_store: BlobDep,
    format: str = Query("csv"),
) -> StreamingResponse:
    """Stream the export AND record an export_jobs row + stored artifact so a
    share link exists for every export (guide §6.2)."""
    if format not in CONTENT_TYPES:
        raise HTTPException(422, "format must be csv|json|xlsx")
    run = _owned_run(db, principal.org_id, forecast_id)
    if run.status != "completed":
        raise HTTPException(409, f"forecast is not completed (status={run.status})")
    _, payload = create_export(db, blob_store, run, format, uuid.UUID(principal.user_id))
    filename = f"forecast_{run.id}.{format}"
    return StreamingResponse(
        iter([payload]),
        media_type=CONTENT_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/forecasts/{forecast_id}/share")
def share_forecast(
    forecast_id: uuid.UUID,
    db: DbDep,
    principal: PrincipalDep,
    blob_store: BlobDep,
    format: str = Query("csv"),
) -> dict:
    """Create a shareable expiring link (export_jobs.share_token, guide §6.2)."""
    if format not in CONTENT_TYPES:
        raise HTTPException(422, "format must be csv|json|xlsx")
    run = _owned_run(db, principal.org_id, forecast_id)
    if run.status != "completed":
        raise HTTPException(409, f"forecast is not completed (status={run.status})")
    job, _ = create_export(db, blob_store, run, format, uuid.UUID(principal.user_id))
    assert job.share_token is not None and job.expires_at is not None
    return {
        "share_url": blob_store.signed_url(
            job.share_token, int((job.expires_at - datetime.now(tz=UTC)).total_seconds())
        ),
        "share_token": job.share_token,
        "format": format,
        "expires_at": job.expires_at.isoformat(),
    }


@router.get("/exports/{share_token}")
def download_shared_export(share_token: str, db: DbDep, blob_store: BlobDep) -> StreamingResponse:
    """Public share-link download — the token IS the capability locally
    (doc 1 §6.5); expiry enforced against export_jobs.expires_at."""
    job = db.scalar(select(ExportJob).where(ExportJob.share_token == share_token))
    if job is None or job.file_path is None:
        raise HTTPException(404, "not found")
    if job.expires_at is not None and job.expires_at < datetime.now(tz=UTC):
        raise HTTPException(410, "share link expired")
    payload = blob_store.get(job.file_path)
    filename = f"forecast_{job.forecast_run_id}.{job.format}"
    return StreamingResponse(
        iter([payload]),
        media_type=CONTENT_TYPES[job.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
