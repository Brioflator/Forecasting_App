"""Resource guards (reliability): per-fit work is bounded by construction and
the app sheds load instead of stacking concurrent fits until it dies.

Root cause these defend against: an ever-growing series made single
auto_arima fits take minutes and gigabytes; abandoned/retried requests piled
up on the threadpool until the process ran out of memory.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import ml.app as ml_app
from ml import forecasting
from ml.constants import MAX_CONCURRENT_FITS, MAX_FIT_POINTS
from ml.forecasting import ForecastResult
from shared.models import Point
from shared.synthetic import sample_value


def _minute_series(n: int) -> list[Point]:
    base = datetime(2026, 6, 1, tzinfo=UTC)
    return [
        Point(timestamp=base + timedelta(minutes=i), value=sample_value(i, m=12)) for i in range(n)
    ]


def test_long_series_trains_on_capped_window() -> None:
    n = MAX_FIT_POINTS + 500
    series = _minute_series(n)
    result = forecasting.forecast(series=series, horizon=6, model="ets")
    assert result.metrics["train_points"] == float(MAX_FIT_POINTS)
    # The forecast still continues from the END of the series.
    assert result.points[0]["timestamp"] > series[-1].timestamp


def test_short_series_unaffected_by_window_cap() -> None:
    series = _minute_series(60)
    result = forecasting.forecast(series=series, horizon=6, model="ets")
    assert result.metrics["train_points"] == 60.0


def test_forecast_endpoint_sheds_load_when_saturated(monkeypatch) -> None:
    """With every fit slot busy, a new request gets a fast 503 (which the
    worker treats as a transport failure and retries with backoff) instead of
    queueing unbounded work."""
    release = threading.Event()

    def slow_forecast(**kwargs) -> ForecastResult:
        release.wait(timeout=10)
        return ForecastResult(
            model="ets",
            model_params={},
            frequency="min",
            points=[],
            metrics={},
            warning=None,
        )

    monkeypatch.setattr(ml_app.forecasting, "forecast", slow_forecast)
    monkeypatch.setattr(ml_app, "FIT_GATE_TIMEOUT_S", 0.1)

    client = TestClient(ml_app.app, raise_server_exceptions=False)
    payload = {
        "series": [
            {"timestamp": p.timestamp.isoformat(), "value": p.value} for p in _minute_series(12)
        ],
        "horizon": 3,
    }

    holders = [
        threading.Thread(target=lambda: client.post("/forecast", json=payload))
        for _ in range(MAX_CONCURRENT_FITS)
    ]
    try:
        for t in holders:
            t.start()
        deadline = time.time() + 5
        while ml_app.fit_slots_in_use() < MAX_CONCURRENT_FITS:
            assert time.time() < deadline, "fit slots never saturated"
            time.sleep(0.02)

        resp = client.post("/forecast", json=payload)
        assert resp.status_code == 503
        assert resp.json()["error"] == "busy"

        eda_payload = {"series": payload["series"]}
        resp = client.post("/eda", json=eda_payload)
        assert resp.status_code == 503
    finally:
        release.set()
        for t in holders:
            t.join(timeout=10)

    # Slots are released once fits finish: the service accepts work again.
    deadline = time.time() + 5
    while ml_app.fit_slots_in_use() > 0:
        assert time.time() < deadline, "fit slots leaked"
        time.sleep(0.02)
    resp = client.post("/forecast", json=payload)
    assert resp.status_code == 200


def test_large_seasonal_period_excludes_arima() -> None:
    """ARIMA cost grows with the state-space dimension (~m); a weekly period
    (168) must never reach an ARIMA fit — the candidate set excludes it."""
    series = _minute_series(400)
    result = forecasting.forecast(series=series, horizon=6, seasonal_period=168)
    assert result.model not in {"sarima", "auto_arima"}


def test_explicit_sarima_with_large_m_substitutes_with_warning() -> None:
    series = _minute_series(400)
    result = forecasting.forecast(series=series, horizon=6, model="sarima", seasonal_period=168)
    assert result.model not in {"sarima", "auto_arima"}
    assert result.warning is not None
    assert "sarima" in result.warning.lower()
