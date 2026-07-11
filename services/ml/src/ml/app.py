"""The ml FastAPI app — /forecast, /eda, /healthz. Stateless, no DB, no auth.

Reliability: both fit endpoints run behind a bounded semaphore. Model fits are
CPU-heavy; without the gate, slow/abandoned requests stack up on the request
threadpool until the process runs out of memory (the historical crash mode).
A saturated service answers 503 quickly — the worker treats that as a
transport failure and retries with backoff, so load is shed, not stacked.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ml import eda as eda_mod
from ml import forecasting, sf_engine
from ml.constants import FIT_GATE_TIMEOUT_S, MAX_CONCURRENT_FITS
from ml.errors import InsufficientData, SeriesRejected
from shared.logging_setup import configure_logging
from shared.models import (
    CandidateScore,
    EdaRequest,
    EdaResponse,
    ForecastError,
    ForecastPoint,
    ForecastRequest,
    ForecastResponse,
)
from shared.settings import get_settings

configure_logging("ml", get_settings().log_level)
log = logging.getLogger("ml.app")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Numba JIT warm-up runs off-thread WITHOUT a fit slot: it must not delay
    # startup or block the two real fit slots while it compiles.
    threading.Thread(target=sf_engine.warmup, daemon=True).start()
    yield


app = FastAPI(title="Forecast ML Service", version="0.1.0", lifespan=_lifespan)

_fit_gate = threading.BoundedSemaphore(MAX_CONCURRENT_FITS)
_slots_lock = threading.Lock()
_slots_in_use = 0


def fit_slots_in_use() -> int:
    with _slots_lock:
        return _slots_in_use


def _acquire_fit_slot() -> bool:
    global _slots_in_use
    if not _fit_gate.acquire(timeout=FIT_GATE_TIMEOUT_S):
        return False
    with _slots_lock:
        _slots_in_use += 1
    return True


def _release_fit_slot() -> None:
    global _slots_in_use
    with _slots_lock:
        _slots_in_use -= 1
    _fit_gate.release()


def _busy_response(endpoint: str) -> JSONResponse:
    log.warning("shedding %s request: all %d fit slots busy", endpoint, MAX_CONCURRENT_FITS)
    return JSONResponse(
        status_code=503,
        content={
            "error": "busy",
            "detail": "ml service is at its concurrent fit limit; retry shortly",
        },
        headers={"Retry-After": "5"},
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/forecast", response_model=None)
def forecast_endpoint(req: ForecastRequest) -> ForecastResponse | JSONResponse:
    if not _acquire_fit_slot():
        return _busy_response("/forecast")
    try:
        result = forecasting.forecast(
            series=req.series,
            horizon=req.horizon,
            model=req.model,
            seasonal_period=req.seasonal_period,
            model_params=req.model_params,
            confidence=req.confidence,
        )
    except InsufficientData as exc:
        body = ForecastError(
            error="insufficient_data", detail=str(exc), min_required=exc.min_required
        )
        return JSONResponse(status_code=422, content=body.model_dump())
    except SeriesRejected as exc:
        body = ForecastError(
            error="series_rejected",
            detail=exc.detail,
            min_required=exc.min_required,
            reason=exc.reason,
        )
        return JSONResponse(status_code=422, content=body.model_dump())
    except ValueError as exc:
        body = ForecastError(error="invalid_request", detail=str(exc), min_required=0)
        return JSONResponse(status_code=422, content=body.model_dump())
    finally:
        _release_fit_slot()

    return ForecastResponse(
        model=result.model,
        model_params=result.model_params,
        frequency=result.frequency,
        points=[ForecastPoint(**p) for p in result.points],
        metrics=result.metrics,
        warning=result.warning,
        route=result.route,
        candidates=(
            [CandidateScore.model_validate(c) for c in result.candidates]
            if result.candidates is not None
            else None
        ),
        low_confidence=result.low_confidence,
        confidence_reasons=result.confidence_reasons,
        series_profile=result.series_profile,
        fit_config=result.fit_config,
    )


@app.post("/eda", response_model=None)
def eda_endpoint(req: EdaRequest) -> EdaResponse | JSONResponse:
    if not _acquire_fit_slot():
        return _busy_response("/eda")
    try:
        report = eda_mod.eda(series=req.series, seasonal_period=req.seasonal_period)
    finally:
        _release_fit_slot()
    return EdaResponse(**report)
