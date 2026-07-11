"""The forecast result shape + assembly helpers shared by every engine.

Lives below both the legacy statsmodels executors (forecasting.py) and the
statsforecast engine (sf_engine.py) so neither imports the other.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm


@dataclass
class ForecastResult:
    model: str
    model_params: dict[str, Any]
    frequency: str
    points: list[dict[str, Any]]  # [{timestamp, predicted, lower, upper}]
    metrics: dict[str, float]
    warning: str | None = None
    # Trust surfacing (guide §4 step 6) — populated by the auto pipeline.
    route: str | None = None
    candidates: list[dict[str, Any]] | None = None  # per-candidate CV scores
    low_confidence: bool = False
    confidence_reasons: list[str] = field(default_factory=list)
    series_profile: dict[str, Any] | None = None
    fit_config: dict[str, Any] | None = None  # deterministic re-fit recipe


def z_value(confidence: float) -> float:
    return float(norm.ppf(1 - (1 - confidence) / 2))


def future_index(s: pd.Series, freq: str, horizon: int) -> pd.DatetimeIndex:
    start = s.index[-1] + pd.tseries.frequencies.to_offset(freq)
    return pd.date_range(start=start, periods=horizon, freq=freq)


def assemble_points(
    future_idx: pd.DatetimeIndex,
    pred: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> list[dict[str, Any]]:
    """Build the response points. Everything must be JSON-representable:
    a non-finite prediction means the fit degenerated — raise so the caller
    falls back to the next candidate; non-finite interval bounds collapse onto
    the prediction (zero-width band is honest for a residual-free fit)."""
    if not np.all(np.isfinite(np.asarray(pred, dtype="float64"))):
        raise ValueError("model produced non-finite predictions")
    out: list[dict[str, Any]] = []
    for ts, p, lo, hi in zip(future_idx, pred, lower, upper, strict=True):
        p_f = float(p)
        lo_f = float(lo) if np.isfinite(lo) else p_f
        hi_f = float(hi) if np.isfinite(hi) else p_f
        out.append(
            {"timestamp": ts.to_pydatetime(), "predicted": p_f, "lower": lo_f, "upper": hi_f}
        )
    return out


def clean_metrics(metrics: dict[str, float]) -> dict[str, float]:
    """Drop non-finite diagnostics (e.g. NaN aic on a residual-free fit) —
    they're optional info and NaN is not JSON-compliant."""
    return {k: v for k, v in metrics.items() if isinstance(v, int | float) and math.isfinite(v)}


def merge_warn(*parts: str | None) -> str | None:
    kept = [p for p in parts if p]
    return "; ".join(kept) if kept else None
