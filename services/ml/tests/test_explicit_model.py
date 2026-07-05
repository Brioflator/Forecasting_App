"""Explicit model requests are honored but never blindly (doc 3 §3)."""

from ml import forecasting
from shared.synthetic import demo_series


def test_explicit_sarima_on_short_series_falls_through_with_warning() -> None:
    r = forecasting.forecast(demo_series(10), horizon=3, model="sarima", seasonal_period=12)
    assert r.model != "sarima"
    assert r.warning is not None and "sarima" in r.warning.lower()


def test_explicit_ets_honored() -> None:
    r = forecasting.forecast(demo_series(20), horizon=5, model="ets", seasonal_period=None)
    assert r.model == "ets"


def test_prophet_degrades_honestly() -> None:
    r = forecasting.forecast(demo_series(60), horizon=6, model="prophet", seasonal_period=12)
    assert r.model != "prophet"
    assert r.warning is not None and "prophet" in r.warning.lower()
