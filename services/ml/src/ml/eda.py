"""EDA: stationarity, seasonality, ACF/PACF — with plain-language readings.

The EDA report is a product feature for non-experts (guide §9): every numeric
result carries a one-sentence human reading (doc 3 §2).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ml.constants import SEASONALITY_MODERATE, SEASONALITY_STRONG
from ml.forecasting import autodetect_period
from ml.profile import seasonal_strength
from ml.regularize import cap_fit_window, regularize
from shared.models import Point


def _stationarity(values: np.ndarray) -> dict[str, Any]:
    from statsmodels.tsa.stattools import adfuller

    # adfuller needs some length and variance; guard tiny/constant series.
    if len(values) < 6 or float(np.nanstd(values)) == 0.0:
        return {
            "adf_stat": None,
            "p_value": None,
            "is_stationary": None,
            "plain": "Not enough varied data to test stationarity reliably.",
        }
    try:
        result = adfuller(values, autolag="AIC")
    except Exception:  # noqa: BLE001 — e.g. perfectly periodic/collinear series
        return {
            "adf_stat": None,
            "p_value": None,
            "is_stationary": None,
            "plain": "Stationarity test was inconclusive for this series.",
        }
    stat, p_value = float(result[0]), float(result[1])
    is_stationary = p_value < 0.05
    plain = (
        "This series looks stationary — its statistical behavior is stable over time."
        if is_stationary
        else "This series looks non-stationary — its level or variance drifts over time."
    )
    return {"adf_stat": stat, "p_value": p_value, "is_stationary": is_stationary, "plain": plain}


def _seasonality(values: np.ndarray, m: int | None) -> dict[str, Any]:
    if not m or len(values) < 2 * m:
        return {
            "detected_period": m,
            "strength": 0.0,
            "plain": "No reliable seasonal pattern detected.",
        }
    strength = seasonal_strength(values, m)
    if strength > SEASONALITY_STRONG:
        band = "Strong"
    elif strength >= SEASONALITY_MODERATE:
        band = "Moderate"
    else:
        band = "Weak"
    plain = f"{band} pattern detected (repeats every {m} points)."
    return {"detected_period": m, "strength": strength, "plain": plain}


def _acf_pacf(values: np.ndarray, nlags: int) -> dict[str, Any]:
    from statsmodels.tsa.stattools import acf, pacf

    nlags = int(min(nlags, len(values) - 1))
    if nlags < 1:
        return {"acf": [1.0], "pacf": [1.0], "lags": [0]}
    acf_vals = acf(values, nlags=nlags, fft=True)
    pacf_vals = pacf(values, nlags=min(nlags, len(values) // 2 - 1))
    lags = list(range(len(acf_vals)))
    return {
        "acf": [float(x) for x in acf_vals],
        "pacf": [float(x) for x in pacf_vals],
        "lags": lags,
    }


def eda(series: list[Point], seasonal_period: int | None = None) -> dict[str, Any]:
    reg = regularize(series)
    # Same bounded-window rule as forecasting (robust STL on an unbounded grid
    # is another way to sink the process); the report reflects recent behavior.
    s = cap_fit_window(reg.series)
    values = s.to_numpy(dtype="float64")
    m = seasonal_period or autodetect_period(s)
    return {
        "frequency": reg.frequency,
        "n_points": int(len(values)),
        "stationarity": _stationarity(values),
        "seasonality": _seasonality(values, m),
        "acf_pacf": _acf_pacf(values, nlags=min(40, max(1, len(values) // 2))),
    }
