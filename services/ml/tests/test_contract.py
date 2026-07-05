"""Contract tests (doc 3 §7): malformed requests return structured errors,
never opaque 500s. Exercised through the FastAPI app in-process."""

from fastapi.testclient import TestClient

from ml.app import app
from shared.synthetic import demo_series

client = TestClient(app, raise_server_exceptions=False)


def _payload(series, **extra):
    return {
        "series": [{"timestamp": p.timestamp.isoformat(), "value": p.value} for p in series],
        **extra,
    }


def test_healthz() -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_insufficient_data_structured_error() -> None:
    resp = client.post("/forecast", json=_payload(demo_series(3), horizon=3))
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "insufficient_data"
    assert body["min_required"] == 4


def test_unknown_model_structured_error() -> None:
    resp = client.post("/forecast", json=_payload(demo_series(30), horizon=3, model="wizardry"))
    assert resp.status_code == 422
    assert resp.json()["error"] == "invalid_request"


def test_horizon_zero_rejected() -> None:
    resp = client.post("/forecast", json=_payload(demo_series(30), horizon=0))
    assert resp.status_code == 422


def test_empty_series_rejected() -> None:
    resp = client.post("/forecast", json=_payload([], horizon=3))
    assert resp.status_code == 422


def test_successful_forecast_shape() -> None:
    resp = client.post("/forecast", json=_payload(demo_series(60), horizon=6, seasonal_period=12))
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "sarima"
    assert len(body["points"]) == 6
    assert set(body["points"][0]) == {"timestamp", "predicted", "lower", "upper"}
    assert "in_sample_mape" in body["metrics"]


def test_forecast_degenerate_series_serializes_cleanly() -> None:
    """Regression (live-found): a perfectly periodic series broke SARIMA and
    Holt-Winters AND produced NaN diagnostics that failed JSON encoding. The
    endpoint must return 200 with finite, JSON-clean numbers."""
    import math as _math
    from datetime import UTC, datetime, timedelta

    from shared.models import Point

    base = datetime(2026, 7, 5, 7, 0, tzinfo=UTC)
    series = [
        Point(
            timestamp=base + timedelta(minutes=i), value=50 + 8 * _math.sin(2 * _math.pi * i / 12)
        )
        for i in range(36)
    ]
    resp = client.post("/forecast", json=_payload(series, horizon=12, seasonal_period=12))
    assert resp.status_code == 200, resp.text
    body = resp.json()  # would raise if NaN leaked into the payload
    assert len(body["points"]) == 12
    for p in body["points"]:
        assert p["lower"] <= p["predicted"] <= p["upper"]


def test_eda_never_500s_on_noiseless_periodic_series() -> None:
    # A pure sinusoid makes adfuller's lag regression collinear; the endpoint
    # must degrade to an "inconclusive" reading, never a 500 (doc 3 §1).
    resp = client.post("/eda", json={**_payload(demo_series(36, noise=0.0)), "seasonal_period": 12})
    assert resp.status_code == 200
    assert "plain" in resp.json()["stationarity"]


def test_eda_endpoint_shape() -> None:
    resp = client.post("/eda", json={**_payload(demo_series(60)), "seasonal_period": 12})
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_points"] == 60
    assert "plain" in body["stationarity"]
    assert "plain" in body["seasonality"]
    assert body["acf_pacf"]["acf"][0] == 1.0
