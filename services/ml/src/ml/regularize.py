"""Turn messy polled data into a regular, model-ready series (doc 3 §5).

All forecasting-domain logic lives in `ml` on a pure input, keeping `worker`
dumb: it ships whatever points exist and lets `ml` decide what's forecastable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.constants import GAP_FILL_MAX_CONSECUTIVE, MAX_FIT_POINTS
from shared.models import Point


def cap_fit_window(series: pd.Series) -> pd.Series:
    """Bound work to the most recent ``MAX_FIT_POINTS`` points — the load-bearing
    guard that keeps per-request fit time/memory from growing with a metric's
    lifetime (the OOM fix). A no-op on short series. Both the forecast ladder
    and EDA route through this so the invariant can't drift between them."""
    return series.tail(MAX_FIT_POINTS) if len(series) > MAX_FIT_POINTS else series


# Canonical (seconds, pandas-offset-alias) rungs for frequency inference.
# Modern pandas aliases (2.2+): 's' 'min' 'h' 'D' 'W' 'MS'.
_FREQ_RUNGS: list[tuple[float, str]] = [
    (1, "s"),
    (60, "min"),
    (3600, "h"),
    (86400, "D"),
    (604800, "W"),
    (2_592_000, "MS"),
]


@dataclass
class Regularized:
    series: pd.Series  # DatetimeIndex, regular grid, no NaN
    frequency: str  # pandas offset alias
    impute_frac: float  # fraction of grid points that were imputed


def _infer_frequency(index: pd.DatetimeIndex) -> str:
    if len(index) < 2:
        return "D"
    deltas = np.diff(index.view("int64")) / 1e9  # seconds
    median = float(np.median(deltas))
    if median <= 0:
        return "D"
    # Nearest rung in log space.
    best = min(_FREQ_RUNGS, key=lambda r: abs(np.log(median) - np.log(r[0])))
    return best[1]


def regularize(series: list[Point]) -> Regularized:
    idx = pd.DatetimeIndex([p.timestamp for p in series])
    raw = pd.Series([p.value for p in series], index=idx, dtype="float64")
    # Duplicate timestamps shouldn't occur (upsert), but defend: mean-aggregate.
    raw = raw.groupby(level=0).mean().sort_index()

    freq = _infer_frequency(raw.index)  # type: ignore[arg-type]
    # Resample onto the frequency's own bucket grid. The bucket labels come
    # from the resampler (wall-clock aligned), NOT from a date_range anchored
    # at the first raw timestamp — otherwise an unaligned source (a webhook
    # firing at :12s past each minute) matches zero grid points and the whole
    # series regularizes to NaN.
    resampled = raw.resample(freq).mean()

    missing_before = int(resampled.isna().sum())
    # Bounded interpolation: fill runs up to the cap, leave longer gaps for the
    # tail ffill/bfill (which the impute_frac warning surfaces).
    filled = resampled.interpolate(
        method="time", limit=GAP_FILL_MAX_CONSECUTIVE, limit_area="inside"
    )
    filled = filled.ffill().bfill()

    grid_len = max(len(resampled), 1)
    impute_frac = missing_before / grid_len
    return Regularized(series=filled, frequency=freq, impute_frac=impute_frac)
