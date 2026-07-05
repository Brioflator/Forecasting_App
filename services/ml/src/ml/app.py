"""The ml FastAPI app — /forecast, /eda, /healthz. Stateless, no DB, no auth."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ml import eda as eda_mod
from ml import forecasting
from ml.errors import InsufficientData
from shared.logging_setup import configure_logging
from shared.models import (
    EdaRequest,
    EdaResponse,
    ForecastError,
    ForecastPoint,
    ForecastRequest,
    ForecastResponse,
)
from shared.settings import get_settings

configure_logging("ml", get_settings().log_level)
app = FastAPI(title="Forecast ML Service", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/forecast", response_model=None)
def forecast_endpoint(req: ForecastRequest) -> ForecastResponse | JSONResponse:
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
    except ValueError as exc:
        body = ForecastError(error="invalid_request", detail=str(exc), min_required=0)
        return JSONResponse(status_code=422, content=body.model_dump())

    return ForecastResponse(
        model=result.model,
        model_params=result.model_params,
        frequency=result.frequency,
        points=[ForecastPoint(**p) for p in result.points],
        metrics=result.metrics,
        warning=result.warning,
    )


@app.post("/eda", response_model=EdaResponse)
def eda_endpoint(req: EdaRequest) -> EdaResponse:
    report = eda_mod.eda(series=req.series, seasonal_period=req.seasonal_period)
    return EdaResponse(**report)
