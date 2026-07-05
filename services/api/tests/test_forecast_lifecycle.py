"""Forecast enqueue → poll lifecycle + CSV export (plan 05 §3 step 6, 8).

The api half of the lifecycle: enqueue creates a pending run, GET reflects
status, and once a run is completed (here simulated inline; the real worker
dispatch is tested in the worker suite) the result and its CSV export read back
correctly."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shared.constants import LOCAL_ORG_ID
from shared.db.models import ForecastPointRow, ForecastRun


def _metric(client: TestClient) -> str:
    cid = client.post(
        "/connectors",
        json={
            "connector_definition_key": "generic_rest",
            "name": "demo",
            "ingestion_method": "pull",
            "config": {"base_url": "http://x/dev/sample-metric", "value_path": "$.value"},
        },
    ).json()["id"]
    return client.post(
        f"/connectors/{cid}/metrics",
        json={"name": "Signups", "key": "sample_signups", "seasonal_period": 12},
    ).json()["id"]


def test_enqueue_creates_pending_run(client: TestClient) -> None:
    mid = _metric(client)
    resp = client.post(f"/metrics/{mid}/forecast", json={"horizon": 12, "model": "auto"})
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["model_type"] == "auto"
    assert body["horizon"] == 12

    polled = client.get(f"/forecasts/{body['id']}").json()
    assert polled["status"] == "pending"
    assert polled["points"] == []


def test_completed_forecast_reads_back_and_exports_csv(
    client: TestClient, db_session: Session
) -> None:
    mid = _metric(client)
    run_id = client.post(f"/metrics/{mid}/forecast", json={"horizon": 3}).json()["id"]

    # Simulate the worker completing the run.
    run = db_session.get(ForecastRun, uuid.UUID(run_id))
    assert run is not None
    run.status = "completed"
    run.completed_at = datetime.now(tz=UTC)
    run.model_params = {"order": [1, 0, 0], "m": 12, "warning": None}
    base = datetime(2026, 7, 1, tzinfo=UTC)
    for i in range(3):
        db_session.add(
            ForecastPointRow(
                forecast_run_id=run.id,
                timestamp=base + timedelta(minutes=i),
                predicted_value=10.0 + i,
                lower_bound=9.0 + i,
                upper_bound=11.0 + i,
            )
        )
    db_session.flush()

    result = client.get(f"/forecasts/{run_id}").json()
    assert result["status"] == "completed"
    assert len(result["points"]) == 3
    assert result["points"][0]["predicted"] == 10.0

    export = client.get(f"/forecasts/{run_id}/export?format=csv")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    text = export.text
    assert "timestamp,actual,forecast,lower,upper" in text
    assert text.count("\n") >= 4  # header + 3 forecast rows


def test_export_rejects_incomplete(client: TestClient) -> None:
    mid = _metric(client)
    run_id = client.post(f"/metrics/{mid}/forecast", json={"horizon": 3}).json()["id"]
    resp = client.get(f"/forecasts/{run_id}/export?format=csv")
    assert resp.status_code == 409


def test_export_rejects_unknown_format(client: TestClient, db_session: Session) -> None:
    mid = _metric(client)
    run_id = client.post(f"/metrics/{mid}/forecast", json={"horizon": 3}).json()["id"]
    run = db_session.get(ForecastRun, uuid.UUID(run_id))
    assert run is not None
    run.status = "completed"
    db_session.flush()
    assert client.get(f"/forecasts/{run_id}/export?format=pdf").status_code == 422


def test_forecast_not_found(client: TestClient) -> None:
    assert client.get(f"/forecasts/{uuid.uuid4()}").status_code == 404


def test_dev_sample_metric_local(client: TestClient) -> None:
    resp = client.get("/dev/sample-metric")
    assert resp.status_code == 200
    body = resp.json()
    assert "value" in body and "timestamp" in body
    assert LOCAL_ORG_ID  # sanity: fixtures imported
