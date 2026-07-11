"""The StatsForecast engine — the only module that imports statsforecast.

Wraps Nixtla models behind CandidateSpec so routing/backtest stay
engine-agnostic and the service still boots (legacy statsmodels ladder) when
statsforecast isn't installable. Budget discipline: the AutoARIMA search reuses
the same bounds that ended the pmdarima OOM incident, CV work is bounded by
routing (≤ MAX_CANDIDATES) and backtest (≤ CV_MAX_FOLDS), and fits stay behind
app.py's semaphore. n_jobs=1 everywhere — determinism over parallelism.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

import numpy as np
import pandas as pd

from ml.constants import (
    AUTO_ARIMA_MAX_P,
    AUTO_ARIMA_MAX_Q,
    AUTO_ARIMA_MAX_SEASONAL,
    TSB_ALPHA_D,
    TSB_ALPHA_P,
)
from ml.results import ForecastResult, assemble_points, z_value
from ml.routing import CandidateSpec

log = logging.getLogger("ml.sf_engine")

# Sparse-demand models have no analytic intervals; theirs come from
# residual widening (same honest recipe as the legacy executors).
_INTERVAL_CAPABLE = {"auto_arima", "auto_ets", "auto_theta", "seasonal_naive", "naive"}


@functools.cache
def available() -> bool:
    try:
        import statsforecast  # noqa: F401
    except Exception as exc:  # noqa: BLE001 — any import failure means "engine off"
        log.warning("statsforecast unavailable, using legacy engine: %s", exc)
        return False
    return True


def engine_version() -> str:
    import statsforecast

    return str(statsforecast.__version__)


def _make_model(spec: CandidateSpec) -> Any:
    from statsforecast.models import (
        TSB,
        AutoARIMA,
        AutoETS,
        AutoTheta,
        CrostonOptimized,
        Naive,
        SeasonalNaive,
    )

    m = spec.m or 1
    if spec.name == "auto_arima":
        return AutoARIMA(
            season_length=m,
            max_p=AUTO_ARIMA_MAX_P,
            max_q=AUTO_ARIMA_MAX_Q,
            max_P=AUTO_ARIMA_MAX_SEASONAL,
            max_Q=AUTO_ARIMA_MAX_SEASONAL,
            alias=spec.name,
        )
    if spec.name == "auto_ets":
        return AutoETS(season_length=m, alias=spec.name)
    if spec.name == "auto_theta":
        return AutoTheta(season_length=m, alias=spec.name)
    if spec.name == "seasonal_naive":
        return SeasonalNaive(season_length=m, alias=spec.name) if spec.m else Naive(alias=spec.name)
    if spec.name == "naive":
        return Naive(alias=spec.name)
    if spec.name == "croston":
        return CrostonOptimized(alias=spec.name)
    if spec.name == "tsb":
        return TSB(alpha_d=TSB_ALPHA_D, alpha_p=TSB_ALPHA_P, alias=spec.name)
    raise ValueError(f"unknown candidate spec: {spec.name!r}")


def _frame(s: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"unique_id": "s", "ds": s.index, "y": s.to_numpy(dtype="float64")})


def cross_validate(
    specs: list[CandidateSpec],
    s: pd.Series,
    freq: str,
    h_cv: int,
    n_windows: int,
) -> pd.DataFrame:
    """Rolling-origin CV over all candidates in one vectorized call.
    Returns the tidy frame backtest.score_candidates consumes
    (ds, cutoff, y, one column per candidate alias). Point scores only —
    no interval computation inside CV."""
    from statsforecast import StatsForecast

    sf = StatsForecast(models=[_make_model(sp) for sp in specs], freq=freq, n_jobs=1)
    return sf.cross_validation(df=_frame(s), h=h_cv, n_windows=n_windows, step_size=h_cv)


def fit_predict(
    spec: CandidateSpec,
    s: pd.Series,
    freq: str,
    horizon: int,
    confidence: float,
) -> ForecastResult:
    """Final fit of the selected candidate, with prediction intervals."""
    from statsforecast import StatsForecast

    sf = StatsForecast(models=[_make_model(spec)], freq=freq, n_jobs=1)
    level = int(round(confidence * 100))
    if spec.name in _INTERVAL_CAPABLE:
        fc = sf.forecast(df=_frame(s), h=horizon, level=[level])
        pred = fc[spec.name].to_numpy(dtype="float64")
        lower = fc[f"{spec.name}-lo-{level}"].to_numpy(dtype="float64")
        upper = fc[f"{spec.name}-hi-{level}"].to_numpy(dtype="float64")
    else:
        fc = sf.forecast(df=_frame(s), h=horizon)
        pred = fc[spec.name].to_numpy(dtype="float64")
        y = s.to_numpy(dtype="float64")
        resid = np.diff(y)
        sigma = float(np.nanstd(resid, ddof=1)) if resid.size > 1 else 0.0
        half = z_value(confidence) * sigma * np.sqrt(np.arange(1, horizon + 1, dtype="float64"))
        lower, upper = pred - half, pred + half

    params: dict[str, Any] = {}
    if spec.m:
        params["m"] = spec.m
    if spec.name == "tsb":
        params["alpha_d"] = TSB_ALPHA_D
        params["alpha_p"] = TSB_ALPHA_P
    return ForecastResult(
        model=spec.name,
        model_params=params,
        frequency=freq,
        points=assemble_points(pd.DatetimeIndex(fc["ds"]), pred, lower, upper),
        metrics={},
    )


def warmup() -> None:
    """Absorb the first-process numba JIT cost at startup instead of on the
    first real request (which the worker times out at 120s)."""
    if not available():
        return
    try:
        idx = pd.date_range("2026-01-01", periods=16, freq="D")
        s = pd.Series(np.sin(np.arange(16.0)) + 10.0, index=idx)
        fit_predict(CandidateSpec("auto_ets"), s, "D", 2, 0.95)
        log.info("statsforecast warm-up complete")
    except Exception as exc:  # noqa: BLE001 — warm-up is best-effort
        log.warning("statsforecast warm-up failed: %s", exc)
