"""The model-selection ladder and its executors (doc 3 §3–§6, plan 05 §2.4).

Design invariants a reviewer holds this to:
- All policy (thresholds, ladder order) lives in `forecast()`; the executors
  are dumb. Tuning behavior = editing constants + the ladder, nowhere else.
- Confidence intervals come from the model / honest residual widening, never a
  fixed multiplier — they widen with horizon and uncertainty.
- Deterministic for fixed input + params (golden-file testing, doc 3 §7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from ml.constants import (
    ABS_MIN,
    AUTO_ARIMA_MAX_P,
    AUTO_ARIMA_MAX_Q,
    AUTO_ARIMA_MAX_SEASONAL,
    AUTO_ARIMA_MAXITER,
    CANDIDATE_PERIODS,
    GAP_FILL_MAX_FRACTION,
    SARIMA_MAX_M,
    SEASONALITY_ACF_THRESHOLD,
    TREND_MIN,
    seasonal_min,
)
from ml.errors import InsufficientData
from ml.regularize import cap_fit_window, regularize
from shared.models import Point

VALID_MODELS = {"auto", "sarima", "ets", "prophet"}


@dataclass
class ForecastResult:
    model: str
    model_params: dict[str, Any]
    frequency: str
    points: list[dict[str, Any]]  # [{timestamp, predicted, lower, upper}]
    metrics: dict[str, float]
    warning: str | None = None


# ── helpers (plan 05 §2.4) ────────────────────────────────────────────────


def autodetect_period(s: pd.Series) -> int | None:
    """Candidate-ACF seasonal period detection (deterministic, cheap)."""
    n = len(s)
    candidates = [m for m in CANDIDATE_PERIODS if m <= n // 2]
    if not candidates:
        return None
    diff = np.diff(np.asarray(s, dtype="float64"))  # remove trend
    diff = diff - diff.mean()
    denom = float(np.dot(diff, diff))
    if denom == 0:
        return None
    best_m: int | None = None
    best_acf = -np.inf
    for m in candidates:
        if m >= len(diff):
            continue
        acf = float(np.dot(diff[:-m], diff[m:]) / denom)
        if acf > best_acf:
            best_acf = acf
            best_m = m
    if best_m is not None and best_acf >= SEASONALITY_ACF_THRESHOLD:
        return best_m
    return None


def _z(confidence: float) -> float:
    return float(norm.ppf(1 - (1 - confidence) / 2))


def _mape(actual: np.ndarray, fitted: np.ndarray) -> float:
    a = np.asarray(actual, dtype="float64")
    f = np.asarray(fitted, dtype="float64")
    mask = ~np.isnan(f) & ~np.isnan(a)
    a, f = a[mask], f[mask]
    if a.size == 0:
        return float("nan")
    if np.any(np.abs(a) < 1e-8):  # switch to sMAPE near zero to avoid blowups
        return float(np.mean(2 * np.abs(a - f) / (np.abs(a) + np.abs(f) + 1e-12)))
    return float(np.mean(np.abs((a - f) / a)))


def _future_index(s: pd.Series, freq: str, horizon: int) -> pd.DatetimeIndex:
    start = s.index[-1] + pd.tseries.frequencies.to_offset(freq)
    return pd.date_range(start=start, periods=horizon, freq=freq)


def _assemble(
    future_idx: pd.DatetimeIndex,
    pred: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> list[dict[str, Any]]:
    """Build the response points. Everything must be JSON-representable:
    a non-finite prediction means the fit degenerated — raise so the ladder
    cascades to the next rung; non-finite interval bounds collapse onto the
    prediction (zero-width band is honest for a residual-free fit)."""
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


def _clean_metrics(metrics: dict[str, float]) -> dict[str, float]:
    """Drop non-finite diagnostics (e.g. NaN aic on a residual-free fit) —
    they're optional info and NaN is not JSON-compliant."""
    import math

    return {k: v for k, v in metrics.items() if isinstance(v, int | float) and math.isfinite(v)}


def _impute_warn(impute_frac: float) -> str | None:
    if impute_frac > GAP_FILL_MAX_FRACTION:
        return f"forecast rests heavily on interpolation ({impute_frac:.0%} of points imputed)"
    return None


def _merge_warn(*parts: str | None) -> str | None:
    kept = [p for p in parts if p]
    return "; ".join(kept) if kept else None


# ── executors (doc 3 §3) ──────────────────────────────────────────────────


def _sarima(
    s: pd.Series, horizon: int, m: int, confidence: float, freq: str, warn: str | None = None
) -> ForecastResult:
    import pmdarima as pm

    model = pm.auto_arima(
        s.to_numpy(),
        seasonal=True,
        m=m,
        max_p=AUTO_ARIMA_MAX_P,
        max_q=AUTO_ARIMA_MAX_Q,
        max_P=AUTO_ARIMA_MAX_SEASONAL,
        max_Q=AUTO_ARIMA_MAX_SEASONAL,
        maxiter=AUTO_ARIMA_MAXITER,
        stepwise=True,
        suppress_warnings=True,
        error_action="ignore",
    )
    pred, ci = model.predict(horizon, return_conf_int=True, alpha=1 - confidence)
    fitted = model.predict_in_sample()
    return ForecastResult(
        model="sarima",
        model_params={
            "order": list(model.order),
            "seasonal_order": list(model.seasonal_order),
            "m": m,
        },
        frequency=freq,
        points=_assemble(_future_index(s, freq, horizon), np.asarray(pred), ci[:, 0], ci[:, 1]),
        metrics=_clean_metrics(
            {"aic": float(model.aic()), "in_sample_mape": _mape(s.to_numpy(), fitted)}
        ),
        warning=warn,
    )


def _exp_smoothing(
    s: pd.Series,
    horizon: int,
    confidence: float,
    freq: str,
    *,
    seasonal_periods: int | None,
    model_name: str,
    warn: str | None,
) -> ForecastResult:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    seasonal = "add" if seasonal_periods else None
    fit = ExponentialSmoothing(
        s.to_numpy(),
        trend="add",
        seasonal=seasonal,
        seasonal_periods=seasonal_periods,
        initialization_method="estimated",
    ).fit()
    pred = np.asarray(fit.forecast(horizon), dtype="float64")
    resid = s.to_numpy() - np.asarray(fit.fittedvalues, dtype="float64")
    sigma = float(np.nanstd(resid, ddof=1)) if np.isfinite(resid).sum() > 1 else 0.0
    z = _z(confidence)
    steps = np.arange(1, horizon + 1, dtype="float64")
    half = z * sigma * np.sqrt(steps)
    params: dict[str, Any] = {"trend": "add", "seasonal": seasonal}
    if seasonal_periods:
        params["seasonal_periods"] = seasonal_periods
    return ForecastResult(
        model=model_name,
        model_params=params,
        frequency=freq,
        points=_assemble(_future_index(s, freq, horizon), pred, pred - half, pred + half),
        metrics=_clean_metrics(
            {
                "aic": float(fit.aic) if np.isfinite(fit.aic) else float("nan"),
                "in_sample_mape": _mape(s.to_numpy(), np.asarray(fit.fittedvalues)),
            }
        ),
        warning=warn,
    )


def _holt_winters(
    s: pd.Series, horizon: int, m: int, confidence: float, freq: str, warn: str | None = None
) -> ForecastResult:
    return _exp_smoothing(
        s, horizon, confidence, freq, seasonal_periods=m, model_name="holt_winters", warn=warn
    )


def _ets_trend(
    s: pd.Series, horizon: int, confidence: float, freq: str, warn: str | None = None
) -> ForecastResult:
    return _exp_smoothing(
        s, horizon, confidence, freq, seasonal_periods=None, model_name="ets", warn=warn
    )


def _seasonal_naive(
    s: pd.Series,
    horizon: int,
    m: int | None,
    confidence: float,
    freq: str,
    warn: str | None = None,
) -> ForecastResult:
    """Seasonal-naive when m is known, else drift — the honest floor (doc 3 §3)."""
    y = s.to_numpy(dtype="float64")
    n = len(y)
    z = _z(confidence)
    steps = np.arange(1, horizon + 1, dtype="float64")

    if m and n >= m:
        # Repeat the last full seasonal cycle forward.
        last_cycle = y[-m:]
        pred = np.array([last_cycle[(i) % m] for i in range(horizon)], dtype="float64")
        onestep_resid = y[m:] - y[:-m]  # seasonal one-step residuals
        model_name = "seasonal_naive"
        params: dict[str, Any] = {"m": m}
    else:
        # Drift: last value + average per-step change.
        slope = (y[-1] - y[0]) / (n - 1) if n > 1 else 0.0
        pred = y[-1] + slope * steps
        onestep_resid = np.diff(y) - slope
        model_name = "drift"
        params = {}

    sigma = float(np.nanstd(onestep_resid, ddof=1)) if onestep_resid.size > 1 else 0.0
    half = z * sigma * np.sqrt(steps)
    # In-sample one-step naive fit for a MAPE diagnostic.
    if m and n >= m:
        fitted = np.concatenate([np.full(m, np.nan), y[:-m]])
    else:
        slope = (y[-1] - y[0]) / (n - 1) if n > 1 else 0.0
        fitted = np.concatenate([[np.nan], y[:-1] + slope])
    return ForecastResult(
        model=model_name,
        model_params=params,
        frequency=freq,
        points=_assemble(_future_index(s, freq, horizon), pred, pred - half, pred + half),
        metrics=_clean_metrics({"in_sample_mape": _mape(y, fitted)}),
        warning=warn,
    )


# ── the ladder (doc 3 §3, plan 05 §2.4) ───────────────────────────────────


def _try_explicit(
    model: str,
    s: pd.Series,
    horizon: int,
    m: int | None,
    confidence: float,
    freq: str,
    impute_warn: str | None,
) -> ForecastResult:
    """Honor an explicit model request; on failure fall through the ladder
    with a warning explaining the substitution (doc 3 §3) — never a hard error."""
    try:
        if model == "sarima":
            if m and m > SARIMA_MAX_M:
                raise ValueError(f"seasonal period {m} exceeds the SARIMA bound of {SARIMA_MAX_M}")
            if m and len(s) >= seasonal_min(m):
                return _sarima(s, horizon, m, confidence, freq, warn=impute_warn)
            raise ValueError("series too short / no period for SARIMA")
        if model == "ets":
            if m and len(s) >= seasonal_min(m):
                return _holt_winters(s, horizon, m, confidence, freq, warn=impute_warn)
            if len(s) >= TREND_MIN:
                return _ets_trend(s, horizon, confidence, freq, warn=impute_warn)
            raise ValueError("series too short for ETS")
        if model == "prophet":
            # Prophet is out of the POC dependency closure; degrade honestly.
            raise ValueError("prophet not available in this build")
    except Exception as exc:  # noqa: BLE001 — substitution is the intended behavior
        substituted = _auto_ladder(s, horizon, m, confidence, freq, impute_warn)
        substituted.warning = _merge_warn(
            f"requested model '{model}' unavailable ({exc}); used {substituted.model}",
            substituted.warning,
        )
        return substituted
    raise AssertionError("unreachable")  # pragma: no cover


def _auto_ladder(
    s: pd.Series,
    horizon: int,
    m: int | None,
    confidence: float,
    freq: str,
    impute_warn: str | None,
) -> ForecastResult:
    # ANY executor failure cascades to the next rung — a degenerate series
    # (e.g. perfectly periodic, near-zero residual variance) can break SARIMA
    # *and* Holt-Winters, and the promise (doc 3 §3) is that a forecast is
    # always returned once past the absolute minimum. The naive floor is pure
    # arithmetic and cannot fail.
    fall_warn: str | None = None

    if m and len(s) >= seasonal_min(m):
        # SARIMA cost grows with the state-space dimension (~m), so large
        # periods (e.g. weekly=168) go straight to Holt-Winters, which handles
        # long seasonality in O(n). This bounds the worst-case fit time.
        if m <= SARIMA_MAX_M:
            try:
                return _sarima(s, horizon, m, confidence, freq, warn=impute_warn)
            except Exception:  # noqa: BLE001 — in-family fallback (plan 05 §2.4)
                fall_warn = "SARIMA fit failed; fell back"
        try:
            return _holt_winters(
                s,
                horizon,
                m,
                confidence,
                freq,
                warn=_merge_warn(
                    f"{fall_warn} to Holt-Winters" if fall_warn else None,
                    impute_warn,
                ),
            )
        except Exception:  # noqa: BLE001
            fall_warn = (
                "seasonal fits failed; fell back" if fall_warn else "seasonal fit failed; fell back"
            )

    if len(s) >= TREND_MIN:
        try:
            return _ets_trend(
                s,
                horizon,
                confidence,
                freq,
                warn=_merge_warn(
                    f"{fall_warn} to trend-only"
                    if fall_warn
                    else "not enough data for a seasonal model; used trend-only",
                    impute_warn,
                ),
            )
        except Exception:  # noqa: BLE001
            fall_warn = (fall_warn or "trend fit failed") + "; used a naive forecast"

    return _seasonal_naive(
        s,
        horizon,
        m,
        confidence,
        freq,
        warn=_merge_warn(fall_warn or "very short series; used a naive forecast", impute_warn),
    )


def forecast(
    series: list[Point],
    horizon: int,
    model: str = "auto",
    seasonal_period: int | None = None,
    model_params: dict[str, Any] | None = None,
    confidence: float = 0.95,
) -> ForecastResult:
    if model not in VALID_MODELS:
        raise ValueError(f"unknown model: {model!r}")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if len(series) < ABS_MIN:
        raise InsufficientData(min_required=ABS_MIN, received=len(series))

    reg = regularize(series)
    freq = reg.frequency
    # Train on a bounded recent window (see cap_fit_window): per-fit time/memory
    # must not grow with the metric's lifetime, and recent history is what local
    # models actually use.
    s = cap_fit_window(reg.series)
    m = seasonal_period or autodetect_period(s)
    impute_warn = _impute_warn(reg.impute_frac)

    if model != "auto":
        result = _try_explicit(model, s, horizon, m, confidence, freq, impute_warn)
    else:
        result = _auto_ladder(s, horizon, m, confidence, freq, impute_warn)
    result.metrics["train_points"] = float(len(s))
    return result
