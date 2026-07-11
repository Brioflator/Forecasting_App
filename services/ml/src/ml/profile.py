"""Series profile + validation gate (guide §2.6, §4 step 2).

The profile is computed once per request on the regularized series and drives
routing (routing.py) and trust surfacing (it travels in the response). The gate
rejects only asks no model can honestly serve; everything else degrades to the
baseline with an explicit low-confidence flag instead of a silent fallback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from ml.constants import (
    ABS_MIN,
    HORIZON_MAX_FACTOR,
    INTERMITTENT_ZERO_FRAC,
    OUTLIER_MAD_Z,
    OUTLIER_MIN_POINTS,
)
from ml.errors import SeriesRejected


@dataclass(frozen=True)
class SeriesProfile:
    n: int
    frequency: str
    impute_frac: float
    pct_zeros: float
    is_intermittent: bool
    seasonal_period: int | None
    seasonal_strength: float
    variance: float
    n_outliers_winsorized: int
    is_constant: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def seasonal_strength(values: np.ndarray, m: int | None) -> float:
    """STL-based seasonal strength in [0, 1] — the one implementation shared
    by the EDA report and the series profile (they must never disagree)."""
    if not m or len(values) < 2 * m or float(np.nanstd(values)) == 0.0:
        return 0.0
    from statsmodels.tsa.seasonal import STL

    stl = STL(values, period=m, robust=True).fit()
    resid = np.asarray(stl.resid, dtype="float64")
    seasonal = np.asarray(stl.seasonal, dtype="float64")
    var_resid = float(np.var(resid))
    var_rs = float(np.var(resid + seasonal))
    strength = 0.0 if var_rs == 0 else max(0.0, 1.0 - var_resid / var_rs)
    return min(1.0, strength)


def is_intermittent(values: np.ndarray) -> bool:
    """Intermittent = mostly zeros and non-negative (event counts, conversions).
    Negative values mean zeros are a scale artifact, not absent demand."""
    if values.size == 0:
        return False
    pct_zeros = float(np.mean(values == 0.0))
    return pct_zeros >= INTERMITTENT_ZERO_FRAC and bool(np.all(values >= 0.0))


def winsorize_outliers(s: pd.Series, intermittent: bool) -> tuple[pd.Series, int]:
    """Cap (never drop) extreme values so a single glitch can't poison every
    fit downstream (guide §2.6). Detection is a MAD z-score on the residual
    from a short rolling median — robust to trend and level shifts, unlike a
    global z. Skipped for intermittent series, where spikes ARE the signal."""
    if intermittent or len(s) < OUTLIER_MIN_POINTS:
        return s, 0
    med = s.rolling(window=5, center=True, min_periods=1).median()
    resid = s - med
    dev = np.abs(resid - float(np.median(resid)))
    mad = float(np.median(dev))
    if mad > 0.0:
        sigma = mad / 0.6745  # MAD → std of a normal
    else:
        # A locally monotone series has resid == 0 at most points (the median
        # of a monotone window IS its center), so the MAD degenerates exactly
        # when a lone spike matters most. Fall back to the mean absolute
        # deviation — inflated by the spike itself, i.e. conservative.
        mnad = float(np.mean(dev))
        if mnad == 0.0:
            return s, 0
        sigma = mnad / 0.7979
    half = OUTLIER_MAD_Z * sigma
    clipped = s.clip(lower=med - half, upper=med + half)
    return clipped, int((clipped != s).sum())


def build_profile(
    s: pd.Series,
    frequency: str,
    impute_frac: float,
    m: int | None,
    n_outliers_winsorized: int,
) -> SeriesProfile:
    values = s.to_numpy(dtype="float64")
    return SeriesProfile(
        n=int(len(values)),
        frequency=frequency,
        impute_frac=float(impute_frac),
        pct_zeros=float(np.mean(values == 0.0)) if values.size else 0.0,
        is_intermittent=is_intermittent(values),
        seasonal_period=m,
        seasonal_strength=seasonal_strength(values, m),
        variance=float(np.var(values)) if values.size else 0.0,
        n_outliers_winsorized=n_outliers_winsorized,
        is_constant=bool(values.size) and float(np.nanstd(values)) == 0.0,
    )


def gate(n: int, horizon: int) -> None:
    """Reject-with-reason for asks no model can honestly serve. Deliberately
    narrow: anything survivable degrades to the baseline with low_confidence
    instead (never-hard-fail stays intact past this point)."""
    if n < ABS_MIN:
        raise SeriesRejected(
            reason="insufficient_after_regularization",
            detail=(f"series collapsed to {n} points on a regular grid; need at least {ABS_MIN}"),
            min_required=ABS_MIN,
        )
    if horizon > HORIZON_MAX_FACTOR * n:
        raise SeriesRejected(
            reason="horizon_too_long",
            detail=(
                f"horizon {horizon} exceeds {HORIZON_MAX_FACTOR}x the "
                f"{n}-point history; any forecast that far out would be noise"
            ),
        )
