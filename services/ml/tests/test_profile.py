"""Series profile + validation gate (guide §2.6, §4 step 2)."""

import numpy as np
import pandas as pd
import pytest

from ml.constants import ABS_MIN, HORIZON_MAX_FACTOR
from ml.errors import SeriesRejected
from ml.profile import build_profile, gate, is_intermittent, winsorize_outliers


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2026-01-01", periods=len(values), freq="D")
    return pd.Series(np.asarray(values, dtype="float64"), index=idx)


class TestIntermittency:
    def test_mostly_zeros_is_intermittent(self) -> None:
        assert is_intermittent(np.array([0.0, 0.0, 5.0, 0.0, 0.0, 3.0, 0.0, 0.0]))

    def test_dense_series_is_not(self) -> None:
        assert not is_intermittent(np.array([1.0, 2.0, 3.0, 4.0, 0.0]))

    def test_negative_values_disqualify(self) -> None:
        # Zeros next to negatives are a scale artifact, not absent demand.
        assert not is_intermittent(np.array([0.0, 0.0, -5.0, 0.0, 0.0, 3.0]))


class TestWinsorize:
    def test_single_spike_is_capped_not_dropped(self) -> None:
        vals = [10.0] * 30
        vals[15] = 1000.0
        clipped, n = winsorize_outliers(_series(vals), intermittent=False)
        assert n == 1
        assert len(clipped) == 30  # capped, never dropped
        assert clipped.iloc[15] < 1000.0

    def test_clean_series_untouched(self) -> None:
        s = _series([float(i % 7) + 10 for i in range(40)])
        clipped, n = winsorize_outliers(s, intermittent=False)
        assert n == 0
        assert (clipped == s).all()

    def test_intermittent_series_skipped(self) -> None:
        vals = [0.0] * 30
        vals[10] = 500.0  # the spike IS the signal
        clipped, n = winsorize_outliers(_series(vals), intermittent=True)
        assert n == 0
        assert clipped.iloc[10] == 500.0

    def test_too_short_skipped(self) -> None:
        _, n = winsorize_outliers(_series([1.0, 2.0, 100.0]), intermittent=False)
        assert n == 0


class TestGate:
    def test_horizon_beyond_factor_rejected(self) -> None:
        with pytest.raises(SeriesRejected) as exc:
            gate(n=10, horizon=HORIZON_MAX_FACTOR * 10 + 1)
        assert exc.value.reason == "horizon_too_long"

    def test_horizon_at_factor_allowed(self) -> None:
        gate(n=10, horizon=HORIZON_MAX_FACTOR * 10)

    def test_collapsed_series_rejected(self) -> None:
        with pytest.raises(SeriesRejected) as exc:
            gate(n=ABS_MIN - 1, horizon=1)
        assert exc.value.reason == "insufficient_after_regularization"
        assert exc.value.min_required == ABS_MIN


class TestBuildProfile:
    def test_profile_fields(self) -> None:
        vals = [0.0, 0.0, 5.0, 0.0] * 10
        p = build_profile(_series(vals), "D", 0.02, m=4, n_outliers_winsorized=1)
        assert p.n == 40
        assert p.frequency == "D"
        assert p.impute_frac == 0.02
        assert p.pct_zeros == 0.75
        assert p.is_intermittent
        assert p.seasonal_period == 4
        assert p.n_outliers_winsorized == 1
        assert not p.is_constant
        d = p.as_dict()
        assert d["is_intermittent"] is True

    def test_constant_series(self) -> None:
        p = build_profile(_series([7.0] * 20), "D", 0.0, m=None, n_outliers_winsorized=0)
        assert p.is_constant
        assert p.variance == 0.0
        assert p.seasonal_strength == 0.0
