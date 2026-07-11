"""The forecasting pipeline: gate → route → backtest → select → fit.

Design invariants a reviewer holds this to:
- All policy (thresholds, routing, selection) lives in constants.py, routing.py
  and backtest.py; executors (sf_engine + the legacy statsmodels rungs below)
  are dumb. Tuning behavior = editing constants + policy modules, nowhere else.
- Confidence intervals come from the model / honest residual widening, never a
  fixed multiplier — they widen with horizon and uncertainty.
- Deterministic for fixed input + params (golden-file testing, doc 3 §7).
- Never-hard-fail past the gate: any engine failure lands on the pure-arithmetic
  naive floor with an EXPLICIT low_confidence flag — fallback is visible, not
  silent (guide §2.8).

The statsmodels executors and _auto_ladder are the legacy engine, kept for
FORECAST_ENGINE=legacy (statsforecast not installable) and as the floor.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml import sf_engine
from ml.backtest import plan_folds, score_candidates, select
from ml.constants import (
    ABS_MIN,
    CANDIDATE_PERIODS,
    GAP_FILL_MAX_FRACTION,
    SEASONALITY_ACF_THRESHOLD,
    SF_SEASON_MAX_M,
    TREND_MIN,
    seasonal_min,
)
from ml.errors import InsufficientData
from ml.profile import SeriesProfile, build_profile, gate, is_intermittent, winsorize_outliers
from ml.regularize import cap_fit_window, regularize
from ml.results import (
    ForecastResult,
    assemble_points,
    clean_metrics,
    future_index,
    merge_warn,
    z_value,
)
from ml.routing import CandidateSpec, Route, baseline_of, candidates, route
from shared.models import Point
from shared.settings import get_settings

VALID_MODELS = {"auto", "sarima", "ets", "prophet"}


# ── helpers (plan 05 §2.4) ────────────────────────────────────────────────


def autodetect_period(s: pd.Series) -> int | None:
    """Candidate-ACF seasonal period detection (deterministic, cheap)."""
    n = len(s)
    candidates_m = [m for m in CANDIDATE_PERIODS if m <= n // 2]
    if not candidates_m:
        return None
    diff = np.diff(np.asarray(s, dtype="float64"))  # remove trend
    diff = diff - diff.mean()
    denom = float(np.dot(diff, diff))
    if denom == 0:
        return None
    best_m: int | None = None
    best_acf = -np.inf
    for m in candidates_m:
        if m >= len(diff):
            continue
        acf = float(np.dot(diff[:-m], diff[m:]) / denom)
        if acf > best_acf:
            best_acf = acf
            best_m = m
    if best_m is not None and best_acf >= SEASONALITY_ACF_THRESHOLD:
        return best_m
    return None


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


def _impute_warn(impute_frac: float) -> str | None:
    if impute_frac > GAP_FILL_MAX_FRACTION:
        return f"forecast rests heavily on interpolation ({impute_frac:.0%} of points imputed)"
    return None


# ── legacy executors (doc 3 §3) — the FORECAST_ENGINE=legacy rungs ────────


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
    z = z_value(confidence)
    steps = np.arange(1, horizon + 1, dtype="float64")
    half = z * sigma * np.sqrt(steps)
    params: dict[str, Any] = {"trend": "add", "seasonal": seasonal}
    if seasonal_periods:
        params["seasonal_periods"] = seasonal_periods
    return ForecastResult(
        model=model_name,
        model_params=params,
        frequency=freq,
        points=assemble_points(future_index(s, freq, horizon), pred, pred - half, pred + half),
        metrics=clean_metrics(
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
    """Seasonal-naive when m is known, else drift — the honest floor (doc 3 §3).
    Pure arithmetic, cannot fail: every fallback path lands here."""
    y = s.to_numpy(dtype="float64")
    n = len(y)
    z = z_value(confidence)
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
        points=assemble_points(future_index(s, freq, horizon), pred, pred - half, pred + half),
        metrics=clean_metrics({"in_sample_mape": _mape(y, fitted)}),
        warning=warn,
    )


# ── the legacy ladder (doc 3 §3, plan 05 §2.4) ────────────────────────────


def _try_explicit(
    model: str,
    s: pd.Series,
    horizon: int,
    m: int | None,
    confidence: float,
    freq: str,
    impute_warn: str | None,
) -> ForecastResult:
    """Honor an explicit model request on the legacy engine; on failure fall
    through the ladder with a warning explaining the substitution (doc 3 §3)
    — never a hard error."""
    try:
        if model == "sarima":
            # pmdarima was dropped (guide §3): SARIMA is served by the
            # statsforecast engine; the legacy engine has no ARIMA rung.
            raise ValueError("sarima requires the statsforecast engine")
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
        substituted.warning = merge_warn(
            f"requested model '{model}' unavailable ({exc}); used {substituted.model}",
            substituted.warning,
        )
        substituted.low_confidence = True
        substituted.confidence_reasons = ["fallback"]
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
    # (e.g. perfectly periodic, near-zero residual variance) can break
    # Holt-Winters, and the promise (doc 3 §3) is that a forecast is always
    # returned once past the gate. The naive floor is pure arithmetic and
    # cannot fail.
    fall_warn: str | None = None

    if m and len(s) >= seasonal_min(m):
        try:
            return _holt_winters(s, horizon, m, confidence, freq, warn=impute_warn)
        except Exception:  # noqa: BLE001
            fall_warn = "seasonal fit failed; fell back"

    if len(s) >= TREND_MIN:
        try:
            return _ets_trend(
                s,
                horizon,
                confidence,
                freq,
                warn=merge_warn(
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
        warn=merge_warn(fall_warn or "very short series; used a naive forecast", impute_warn),
    )


# ── the statsforecast pipeline (guide §4 steps 3–6) ───────────────────────


def _fit_config(spec: CandidateSpec, result: ForecastResult, confidence: float, n: int) -> dict:
    return {
        "engine": "statsforecast",
        "engine_version": sf_engine.engine_version(),
        "model": spec.name,
        "m": spec.m,
        "confidence": confidence,
        "frequency": result.frequency,
        "train_points": n,
        "params": result.model_params,
    }


def _floor_result(
    s: pd.Series,
    horizon: int,
    m: int | None,
    confidence: float,
    freq: str,
    warn: str | None,
    reasons: list[str],
) -> ForecastResult:
    result = _seasonal_naive(s, horizon, m, confidence, freq, warn=warn)
    result.low_confidence = True
    result.confidence_reasons = reasons
    result.fit_config = {
        "engine": "legacy",
        "model": result.model,
        "m": m,
        "confidence": confidence,
        "frequency": freq,
        "train_points": len(s),
        "params": result.model_params,
    }
    return result


def _explicit_sf(
    model: str,
    s: pd.Series,
    horizon: int,
    m: int | None,
    confidence: float,
    freq: str,
    impute_warn: str | None,
) -> ForecastResult:
    """Explicit model requests keep their pre-CV semantics: the user chose the
    model, so no backtest selection runs. sarima/ets map onto their
    statsforecast successors; any failure substitutes down the legacy ladder."""
    spec_name = {"sarima": "auto_arima", "ets": "auto_ets"}.get(model)
    if spec_name is None:  # prophet — degrade honestly, as before
        return _try_explicit(model, s, horizon, m, confidence, freq, impute_warn)
    try:
        if model == "sarima":
            # Same honesty gates the pmdarima rung had: a seasonal ARIMA needs
            # two full cycles, and a huge m must not reach the fit at all.
            if m and m > SF_SEASON_MAX_M:
                raise ValueError(
                    f"seasonal period {m} exceeds the SARIMA bound of {SF_SEASON_MAX_M}"
                )
            if not (m and len(s) >= seasonal_min(m)):
                raise ValueError("series too short / no period for SARIMA")
            spec = CandidateSpec(spec_name, m)
        else:
            # ETS degrades to trend-only (m=None) below two cycles, as before.
            spec = CandidateSpec(spec_name, m if (m and len(s) >= seasonal_min(m)) else None)
        result = sf_engine.fit_predict(spec, s, freq, horizon, confidence)
    except Exception as exc:  # noqa: BLE001 — substitution is the intended behavior
        substituted = _auto_ladder(s, horizon, m, confidence, freq, impute_warn)
        substituted.warning = merge_warn(
            f"requested model '{model}' failed ({exc}); used {substituted.model}",
            substituted.warning,
        )
        substituted.low_confidence = True
        substituted.confidence_reasons = ["fallback"]
        return substituted
    result.warning = impute_warn
    result.fit_config = _fit_config(spec, result, confidence, len(s))
    return result


def _auto_sf(
    s: pd.Series,
    horizon: int,
    m: int | None,
    confidence: float,
    freq: str,
    impute_warn: str | None,
    profile: SeriesProfile,
) -> ForecastResult:
    """route → CV → select → final fit. Every failure path lands on the naive
    floor with low_confidence=true — fallback is explicit, never silent."""
    rte = route(profile)
    specs = candidates(rte, m)
    baseline = baseline_of(specs)

    chosen = baseline
    low_confidence = False
    reasons: list[str] = []
    cand_scores: list[dict[str, Any]] | None = None
    cv_warn: str | None = None
    chosen_metrics: dict[str, float] = {}

    # Non-seasonal routes ignore m entirely, so a (possibly misdetected)
    # period must not inflate the fold plan's min-train requirement or
    # degenerate the MASE scaling lag.
    plan_m = m if rte is Route.SEASONAL else None
    h_cv, k = plan_folds(len(s), horizon, plan_m)
    if rte is Route.SHORT or k < 1:
        # Too little history to backtest anything — the baseline is the only
        # honest answer, and we say so.
        result = _floor_result(
            s,
            horizon,
            m,
            confidence,
            freq,
            merge_warn("history too short to backtest; used the baseline", impute_warn),
            ["cv_skipped"],
        )
        result.route = rte.value
        return result

    try:
        cv = sf_engine.cross_validate(specs, s, freq, h_cv, k)
        scores = score_candidates(cv, s, [sp.name for sp in specs], plan_m)
        default_name = "auto_ets" if any(sp.name == "auto_ets" for sp in specs) else baseline.name
        sel = select(scores, default_name, baseline.name)
        chosen = next(sp for sp in specs if sp.name == sel.chosen)
        low_confidence = sel.low_confidence
        reasons = sel.reasons
        cand_scores = [c.as_dict() for c in scores]
        chosen_score = next(c for c in scores if c.model == sel.chosen)
        for key, val in (
            ("cv_mase", chosen_score.mean_mase),
            ("cv_smape", chosen_score.mean_smape),
            ("cv_rmse", chosen_score.mean_rmse),
        ):
            if val is not None:
                chosen_metrics[key] = float(val)
    except Exception:  # noqa: BLE001 — CV failure routes to the robust default
        chosen = next((sp for sp in specs if sp.name == "auto_ets"), baseline)
        low_confidence = True
        reasons = ["cv_skipped"]
        cv_warn = "cross-validation failed; fitted the robust default without backtest"

    try:
        result = sf_engine.fit_predict(chosen, s, freq, horizon, confidence)
    except Exception:  # noqa: BLE001 — the floor cannot fail
        result = _floor_result(
            s,
            horizon,
            m,
            confidence,
            freq,
            merge_warn(f"{chosen.name} final fit failed; used the naive floor", impute_warn),
            [*dict.fromkeys([*reasons, "fallback"])],
        )
        result.route = rte.value
        result.candidates = cand_scores
        return result

    result.warning = merge_warn(cv_warn, impute_warn)
    result.route = rte.value
    result.candidates = cand_scores
    result.low_confidence = low_confidence
    result.confidence_reasons = reasons
    result.metrics.update(chosen_metrics)
    result.fit_config = _fit_config(chosen, result, confidence, len(s))
    return result


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
    gate(len(s), horizon)

    # Winsorize BEFORE period detection and profiling: one glitch spike can
    # otherwise poison the ACF and every fit downstream (guide §2.6).
    intermittent = is_intermittent(s.to_numpy(dtype="float64"))
    s, n_winsorized = winsorize_outliers(s, intermittent)
    m = seasonal_period or autodetect_period(s)
    profile = build_profile(s, freq, reg.impute_frac, m, n_winsorized)
    impute_warn = _impute_warn(reg.impute_frac)
    if n_winsorized:
        impute_warn = merge_warn(
            impute_warn, f"{n_winsorized} extreme value(s) capped before fitting"
        )

    use_sf = get_settings().forecast_engine == "statsforecast" and sf_engine.available()
    if model != "auto":
        if use_sf:
            result = _explicit_sf(model, s, horizon, m, confidence, freq, impute_warn)
        else:
            result = _try_explicit(model, s, horizon, m, confidence, freq, impute_warn)
    elif use_sf:
        result = _auto_sf(s, horizon, m, confidence, freq, impute_warn, profile)
    else:
        result = _auto_ladder(s, horizon, m, confidence, freq, impute_warn)
        result.warning = merge_warn(
            "statistical engine unavailable; used legacy ladder", result.warning
        )
        result.low_confidence = True
        result.confidence_reasons = ["cv_skipped"]

    result.series_profile = profile.as_dict()
    result.metrics["train_points"] = float(len(s))
    return result
