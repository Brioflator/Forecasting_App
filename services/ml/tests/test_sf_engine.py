"""StatsForecast engine smoke + determinism. Skipped wholesale when the
engine isn't installed (FORECAST_ENGINE=legacy machines)."""

import numpy as np
import pandas as pd
import pytest

from ml import sf_engine
from ml.routing import CandidateSpec

pytestmark = pytest.mark.skipif(not sf_engine.available(), reason="statsforecast not installed")


def _series(n: int = 72, m: int = 12) -> pd.Series:
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    t = np.arange(n, dtype="float64")
    return pd.Series(100 + 0.1 * t + 8 * np.sin(2 * np.pi * t / m), index=idx)


def test_fit_predict_shape_and_intervals() -> None:
    r = sf_engine.fit_predict(CandidateSpec("auto_ets", 12), _series(), "h", 6, 0.95)
    assert r.model == "auto_ets"
    assert len(r.points) == 6
    assert all(p["lower"] <= p["predicted"] <= p["upper"] for p in r.points)
    # The forecast continues the hourly grid.
    assert r.points[1]["timestamp"] - r.points[0]["timestamp"] == pd.Timedelta(hours=1)


def test_sparse_models_get_residual_intervals() -> None:
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    vals = np.zeros(60)
    vals[::5] = 7.0
    s = pd.Series(vals, index=idx)
    r = sf_engine.fit_predict(CandidateSpec("croston"), s, "D", 5, 0.95)
    assert len(r.points) == 5
    assert all(p["lower"] <= p["predicted"] <= p["upper"] for p in r.points)


def test_cross_validation_frame_shape() -> None:
    specs = [CandidateSpec("auto_ets", 12), CandidateSpec("seasonal_naive", 12)]
    cv = sf_engine.cross_validate(specs, _series(), "h", h_cv=6, n_windows=2)
    assert {"ds", "cutoff", "y", "auto_ets", "seasonal_naive"} <= set(cv.columns)
    assert cv["cutoff"].nunique() == 2
    assert len(cv) == 12  # 2 folds × h_cv=6


def test_deterministic_across_calls() -> None:
    a = sf_engine.fit_predict(CandidateSpec("auto_arima", 12), _series(), "h", 6, 0.95)
    b = sf_engine.fit_predict(CandidateSpec("auto_arima", 12), _series(), "h", 6, 0.95)
    for pa, pb in zip(a.points, b.points, strict=True):
        assert pa["predicted"] == pytest.approx(pb["predicted"], rel=1e-9)
        assert pa["lower"] == pytest.approx(pb["lower"], rel=1e-9)


def test_warmup_never_raises() -> None:
    sf_engine.warmup()


def test_unknown_spec_rejected() -> None:
    with pytest.raises(ValueError):
        sf_engine.fit_predict(CandidateSpec("wizardry"), _series(), "h", 3, 0.95)
