"""Pipeline coverage (doc 3 §7): feed a series engineered to land on each
route/path and assert model family, trust flags, and interval sanity."""

import pytest

from ml import forecasting
from ml.errors import InsufficientData, SeriesRejected
from shared.synthetic import demo_series

SEASONAL_FAMILY = {"auto_ets", "auto_arima", "auto_theta", "seasonal_naive"}
NON_SEASONAL_FAMILY = {"auto_ets", "auto_theta", "naive"}


def test_refuse_below_absolute_floor() -> None:
    with pytest.raises(InsufficientData) as exc:
        forecasting.forecast(demo_series(3), horizon=3)
    assert exc.value.min_required == 4


def test_reject_horizon_beyond_history() -> None:
    with pytest.raises(SeriesRejected) as exc:
        forecasting.forecast(demo_series(10), horizon=100)
    assert exc.value.reason == "horizon_too_long"


def test_short_series_gets_explicit_low_confidence_baseline() -> None:
    r = forecasting.forecast(demo_series(6), horizon=3, seasonal_period=None)
    assert r.model in {"drift", "seasonal_naive"}
    assert r.low_confidence
    assert r.confidence_reasons == ["cv_skipped"]
    assert r.route == "short"
    assert r.warning is not None
    assert len(r.points) == 3


def test_non_seasonal_route_runs_cv() -> None:
    r = forecasting.forecast(demo_series(40, amplitude=0.0, trend=0.5), horizon=5)
    assert r.model in SEASONAL_FAMILY | NON_SEASONAL_FAMILY
    assert r.candidates is not None and len(r.candidates) >= 2
    assert r.fit_config is not None and r.fit_config["engine"] == "statsforecast"


def test_seasonal_route_with_known_period() -> None:
    r = forecasting.forecast(demo_series(60), horizon=12, seasonal_period=12)
    assert r.route == "seasonal"
    assert r.model in SEASONAL_FAMILY
    assert r.series_profile is not None and r.series_profile["seasonal_period"] == 12
    assert "cv_mase" in r.metrics
    assert len(r.points) == 12
    assert all(p["lower"] <= p["predicted"] <= p["upper"] for p in r.points)
    # Per-candidate fold scores are surfaced for the UI (guide §4 step 4).
    assert r.candidates is not None
    assert any(c["model"] == "seasonal_naive" for c in r.candidates)


def test_auto_detects_period_when_not_supplied() -> None:
    r = forecasting.forecast(demo_series(48, noise=0.5), horizon=6)  # no seasonal_period
    assert r.series_profile is not None and r.series_profile["seasonal_period"] == 12
    assert r.route == "seasonal"


def test_intermittent_series_routes_to_sparse_family() -> None:
    from datetime import UTC, datetime, timedelta

    from shared.models import Point

    base = datetime(2026, 1, 1, tzinfo=UTC)
    vals = [0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 3.0, 0.0] * 10
    series = [Point(timestamp=base + timedelta(days=i), value=v) for i, v in enumerate(vals)]
    r = forecasting.forecast(series, horizon=7)
    assert r.route == "intermittent"
    assert r.model in {"croston", "tsb", "naive"}
    assert r.series_profile is not None and r.series_profile["is_intermittent"]


def test_short_seasonal_series_lands_on_baseline() -> None:
    # m=12 known but only 18 points (< 2m=24) → too few cycles to backtest.
    r = forecasting.forecast(demo_series(18), horizon=4, seasonal_period=12)
    assert r.route == "short"
    assert r.model in {"drift", "seasonal_naive"}
    assert r.low_confidence


def test_degenerate_perfectly_periodic_series_still_forecasts() -> None:
    """Regression: a noise-free 50+8·sin(2πi/12) series broke SARIMA *and* the
    Holt-Winters fallback in the live stack; the pipeline must land on a rung
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


def test_outlier_spike_is_capped_and_reported() -> None:
    points = demo_series(60)
    points[30].value += 500.0  # a glitch spike
    r = forecasting.forecast(points, horizon=6)
    assert r.series_profile is not None
    assert r.series_profile["n_outliers_winsorized"] >= 1
    assert r.warning is not None and "capped" in r.warning


def test_legacy_engine_flagged_low_confidence(monkeypatch) -> None:
    """With statsforecast unavailable, the statsmodels ladder still answers —
    but says so and never claims earned confidence (no CV ran)."""
    from ml import sf_engine

    monkeypatch.setattr(sf_engine, "available", lambda: False)
    r = forecasting.forecast(demo_series(60), horizon=6, seasonal_period=12)
    assert r.model in {"holt_winters", "ets", "seasonal_naive", "drift"}
    assert r.low_confidence
    assert r.confidence_reasons == ["cv_skipped"]
    assert r.warning is not None and "legacy" in r.warning
