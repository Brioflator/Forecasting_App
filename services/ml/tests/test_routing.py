"""Routing policy (guide §4 step 3): hints with fallbacks, baseline always in."""

import pytest

from ml.constants import MAX_CANDIDATES, SF_SEASON_MAX_M
from ml.profile import SeriesProfile
from ml.routing import CandidateSpec, Route, baseline_of, candidates, route


def _profile(
    n: int = 100,
    intermittent: bool = False,
    m: int | None = None,
) -> SeriesProfile:
    return SeriesProfile(
        n=n,
        frequency="D",
        impute_frac=0.0,
        pct_zeros=0.5 if intermittent else 0.0,
        is_intermittent=intermittent,
        seasonal_period=m,
        seasonal_strength=0.7 if m else 0.0,
        variance=1.0,
        n_outliers_winsorized=0,
        is_constant=False,
    )


class TestRoute:
    def test_intermittent_wins_over_everything(self) -> None:
        assert route(_profile(n=100, intermittent=True, m=7)) is Route.INTERMITTENT

    def test_seasonal_with_enough_cycles(self) -> None:
        assert route(_profile(n=100, m=7)) is Route.SEASONAL

    def test_short_when_below_two_cycles(self) -> None:
        assert route(_profile(n=18, m=12)) is Route.SHORT

    def test_short_when_below_trend_min(self) -> None:
        assert route(_profile(n=8)) is Route.SHORT

    def test_non_seasonal_default(self) -> None:
        assert route(_profile(n=50, m=None)) is Route.NON_SEASONAL


class TestCandidates:
    @pytest.mark.parametrize(
        "rte,m",
        [
            (Route.SHORT, None),
            (Route.SHORT, 12),
            (Route.INTERMITTENT, None),
            (Route.SEASONAL, 12),
            (Route.SEASONAL, 168),
            (Route.NON_SEASONAL, None),
        ],
    )
    def test_bounded_and_baseline_last(self, rte: Route, m: int | None) -> None:
        specs = candidates(rte, m)
        assert 1 <= len(specs) <= MAX_CANDIDATES
        assert baseline_of(specs).name in {"seasonal_naive", "naive"}

    def test_seasonal_includes_arima_within_bound(self) -> None:
        names = [sp.name for sp in candidates(Route.SEASONAL, 12)]
        assert names == ["auto_ets", "auto_arima", "auto_theta", "seasonal_naive"]

    def test_large_m_excludes_arima(self) -> None:
        names = [sp.name for sp in candidates(Route.SEASONAL, SF_SEASON_MAX_M + 1)]
        assert "auto_arima" not in names
        assert "auto_ets" in names

    def test_intermittent_uses_sparse_family(self) -> None:
        names = [sp.name for sp in candidates(Route.INTERMITTENT, None)]
        assert names == ["croston", "tsb", "naive"]

    def test_specs_carry_m(self) -> None:
        assert all(sp.m == 12 for sp in candidates(Route.SEASONAL, 12) if sp.name != "naive")
        assert candidates(Route.NON_SEASONAL, None)[0] == CandidateSpec("auto_ets", None)
