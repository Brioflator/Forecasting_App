"""Explicit model requests are honored but never blindly (doc 3 §3).

pmdarima was dropped: explicit "sarima" is served by statsforecast AutoARIMA
and "ets" by AutoETS, with the same honesty gates (two full cycles for a
seasonal fit) and the same substitute-with-warning behavior on failure.
"""

from ml import forecasting
from shared.synthetic import demo_series


def test_explicit_sarima_served_by_auto_arima() -> None:
    r = forecasting.forecast(demo_series(60), horizon=6, model="sarima", seasonal_period=12)
    assert r.model == "auto_arima"
    assert r.model_params.get("m") == 12
    assert not r.low_confidence  # the user chose it; no selection ran
    assert r.fit_config is not None and r.fit_config["engine"] == "statsforecast"


def test_explicit_sarima_on_short_series_falls_through_with_warning() -> None:
    r = forecasting.forecast(demo_series(10), horizon=3, model="sarima", seasonal_period=12)
    assert r.model not in {"sarima", "auto_arima"}
    assert r.warning is not None and "sarima" in r.warning.lower()
    assert r.low_confidence
    assert r.confidence_reasons == ["fallback"]


def test_explicit_ets_honored() -> None:
    r = forecasting.forecast(demo_series(20), horizon=5, model="ets", seasonal_period=None)
    assert r.model == "auto_ets"


def test_explicit_ets_degrades_to_trend_only_below_two_cycles() -> None:
    # m=12 declared but only 20 points → seasonal ETS would be nonsense;
    # served non-seasonally, matching the old ladder's behavior.
    r = forecasting.forecast(demo_series(20), horizon=5, model="ets", seasonal_period=12)
    assert r.model == "auto_ets"
    assert r.model_params.get("m") is None


def test_prophet_degrades_honestly() -> None:
    r = forecasting.forecast(demo_series(60), horizon=6, model="prophet", seasonal_period=12)
    assert r.model != "prophet"
    assert r.warning is not None and "prophet" in r.warning.lower()
    assert r.low_confidence
