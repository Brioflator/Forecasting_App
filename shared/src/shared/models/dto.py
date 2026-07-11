from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Point(BaseModel):
    """One observation of a series (doc 1 §4.1, doc 3 §2)."""

    timestamp: datetime
    value: float


class ForecastRequest(BaseModel):
    """POST /forecast request body (doc 3 §2)."""

    series: list[Point]
    horizon: int
    model: str = "auto"  # "auto" | "sarima" | "ets" | "prophet"
    seasonal_period: int | None = None
    model_params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.95


class ForecastPoint(BaseModel):
    timestamp: datetime
    predicted: float
    lower: float
    upper: float


class FoldScore(BaseModel):
    """One rolling-origin CV fold's error for one candidate (guide §4 step 4)."""

    fold: int
    cutoff: datetime
    mase: float | None = None
    smape: float | None = None
    rmse: float | None = None


class CandidateScore(BaseModel):
    """Backtest summary for one candidate model across all folds."""

    model: str
    mean_mase: float | None = None
    mean_smape: float | None = None
    mean_rmse: float | None = None
    folds: list[FoldScore] = Field(default_factory=list)


class ForecastResponse(BaseModel):
    """POST /forecast success body (doc 3 §2).

    Trust-surfacing fields (guide §4 step 6) are additive with defaults so an
    old worker against a new ml (or the reverse) keeps working during rollout.
    """

    model: str  # the model ACTUALLY used (may differ from request on fallback)
    model_params: dict[str, Any]
    frequency: str  # pandas offset alias ml inferred/used
    points: list[ForecastPoint]
    metrics: dict[str, float]
    warning: str | None = None
    route: str | None = None  # diagnostics route taken (auto mode only)
    candidates: list[CandidateScore] | None = None  # per-candidate CV scores
    low_confidence: bool = False
    confidence_reasons: list[str] = Field(default_factory=list)
    series_profile: dict[str, Any] | None = None
    fit_config: dict[str, Any] | None = None  # deterministic re-fit recipe


class ForecastError(BaseModel):
    """POST /forecast refusal body (doc 3 §2) — too little/broken to forecast."""

    error: str
    detail: str
    min_required: int
    reason: str | None = None  # machine-readable gate slug, e.g. "horizon_too_long"


class EdaRequest(BaseModel):
    series: list[Point]
    seasonal_period: int | None = None


class EdaResponse(BaseModel):
    frequency: str
    n_points: int
    stationarity: dict[str, Any]
    seasonality: dict[str, Any]
    acf_pacf: dict[str, Any]


class IngestPayload(BaseModel):
    """Agent → api and webhook → api ingestion contract (doc 1 §5.3)."""

    metric_key: str
    points: list[Point]
