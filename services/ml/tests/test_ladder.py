"""One test per ladder rung (doc 3 §7 ladder-coverage): feed a series
engineered to land on exactly that rung and assert model + warning."""

import pytest

from ml import forecasting
from ml.errors import InsufficientData
from shared.synthetic import demo_series


def test_refuse_below_absolute_floor() -> None:
    with pytest.raises(InsufficientData) as exc:
        forecasting.forecast(demo_series(3), horizon=3)
    assert exc.value.min_required == 4


def test_drift_floor_very_short() -> None:
    r = forecasting.forecast(demo_series(6), horizon=3, seasonal_period=None)
    assert r.model in {"drift", "seasonal_naive"}
    assert r.warning is not None and "naive" in r.warning
    assert len(r.points) == 3


def test_trend_only_rung() -> None:
    r = forecasting.forecast(demo_series(15), horizon=5, seasonal_period=None)
    assert r.model == "ets"
    assert r.warning is not None and "trend-only" in r.warning


def test_sarima_rung_with_known_period() -> None:
    r = forecasting.forecast(demo_series(60), horizon=12, seasonal_period=12)
    assert r.model == "sarima"
    assert r.model_params["m"] == 12
    assert r.warning is None
    assert len(r.points) == 12
    assert all(p["lower"] <= p["predicted"] <= p["upper"] for p in r.points)


def test_auto_detects_period_when_not_supplied() -> None:
    r = forecasting.forecast(demo_series(48, noise=0.5), horizon=6)  # no seasonal_period
    assert r.model == "sarima"
    assert r.model_params["m"] == 12


def test_short_seasonal_series_drops_to_trend_only() -> None:
    # m=12 known but only 18 points (< 2m=24) → not enough cycles → trend-only
    r = forecasting.forecast(demo_series(18), horizon=4, seasonal_period=12)
    assert r.model == "ets"
    assert r.warning is not None


def test_degenerate_perfectly_periodic_series_still_forecasts() -> None:
    """Regression: a noise-free 50+8·sin(2πi/12) series broke SARIMA *and* the
    Holt-Winters fallback in the live stack; the ladder must cascade to a rung
    that works instead of surfacing the executor error (doc 3 §3)."""
    import math
    from datetime import UTC, datetime, timedelta

    from shared.models import Point

    base = datetime(2026, 7, 5, 7, 0, tzinfo=UTC)
    series = [
        Point(
            timestamp=base + timedelta(minutes=i),
            value=50 + 8 * math.sin(2 * math.pi * i / 12),
        )
        for i in range(36)
    ]
    r = forecasting.forecast(series, horizon=12, seasonal_period=12)
    assert len(r.points) == 12
    assert all(p["lower"] <= p["predicted"] <= p["upper"] for p in r.points)


def test_intervals_widen_with_horizon() -> None:
    r = forecasting.forecast(demo_series(60), horizon=24, seasonal_period=12)
    widths = [p["upper"] - p["lower"] for p in r.points]
    assert widths[-1] >= widths[0]
