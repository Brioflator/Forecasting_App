"""The 'whole product' API surface: notifications, dashboard, CRUD lifecycle,
forecast history, anomalies listing, connector runs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.constants import LOCAL_ORG_ID
from shared.db.models import (
    Anomaly,
    ConnectorRun,
    ForecastRun,
    Metric,
    Notification,
)


def _connector(client: TestClient, method: str = "pull") -> str:
    return client.post(
        "/connectors",
        json={
            "connector_definition_key": "generic_rest",
            "name": "demo",
            "ingestion_method": method,
            "config": {"base_url": "http://x", "value_path": "$.v"},
        },
    ).json()["id"]


def _metric(client: TestClient, cid: str, key: str = "k") -> str:
    return client.post(
        f"/connectors/{cid}/metrics", json={"name": key, "key": key, "seasonal_period": 12}
    ).json()["id"]


# ── notifications ─────────────────────────────────────────────────────────


def _note(db_session: Session, type_: str = "forecast_completed") -> Notification:
    n = Notification(organization_id=uuid.UUID(LOCAL_ORG_ID), type=type_, payload={"x": 1})
    db_session.add(n)
    db_session.flush()
    return n


def test_notifications_list_read_and_read_all(client: TestClient, db_session: Session) -> None:
    _note(db_session)
    n2 = _note(db_session, "anomaly_detected")

    listing = client.get("/notifications").json()
    assert len(listing) == 2
    assert all(n["read_at"] is None for n in listing)

    read = client.post(f"/notifications/{n2.id}/read").json()
    assert read["read_at"] is not None

    unread = client.get("/notifications?unread_only=true").json()
    assert len(unread) == 1

    result = client.post("/notifications/read-all").json()
    assert result["marked_read"] == 1
    assert client.get("/notifications?unread_only=true").json() == []


def test_unread_count_endpoint(client: TestClient, db_session: Session) -> None:
    assert client.get("/notifications/unread-count").json() == {"unread": 0}
    _note(db_session)
    n2 = _note(db_session, "anomaly_detected")
    assert client.get("/notifications/unread-count").json() == {"unread": 2}
    client.post(f"/notifications/{n2.id}/read")
    assert client.get("/notifications/unread-count").json() == {"unread": 1}


# ── dashboard ─────────────────────────────────────────────────────────────


def test_dashboard_counts(client: TestClient, db_session: Session) -> None:
    cid = _connector(client)
    _metric(client, cid)
    _note(db_session)
    db_session.add(
        Anomaly(
            organization_id=uuid.UUID(LOCAL_ORG_ID),
            metric_id=uuid.UUID(_metric(client, cid, "k2")),
            detected_at=datetime.now(tz=UTC),
            actual_value=1.0,
            severity="high",
        )
    )
    db_session.flush()

    d = client.get("/dashboard").json()
    assert d["connectors"] == 1
    assert d["metrics"] == 2
    assert d["unread_notifications"] == 1
    assert d["open_anomalies"] == 1
    assert d["connectors_error"] == 0


# ── metric CRUD + history ─────────────────────────────────────────────────


def test_metric_patch_and_delete(client: TestClient, db_session: Session) -> None:
    cid = _connector(client)
    mid = _metric(client, cid)

    patched = client.patch(
        f"/metrics/{mid}", json={"name": "Renamed", "unit": "users", "seasonal_period": 24}
    ).json()
    assert patched["name"] == "Renamed"
    assert patched["seasonal_period"] == 24

    assert client.delete(f"/metrics/{mid}").status_code == 204
    assert client.get(f"/metrics/{mid}").status_code == 404
    assert db_session.scalar(select(Metric).where(Metric.id == uuid.UUID(mid))) is None


def test_forecast_history_lists_runs_newest_first(client: TestClient, db_session: Session) -> None:
    cid = _connector(client)
    mid = _metric(client, cid)
    first = client.post(f"/metrics/{mid}/forecast", json={"horizon": 3}).json()["id"]
    second = client.post(f"/metrics/{mid}/forecast", json={"horizon": 6}).json()["id"]

    # The shared test session gives both runs the same transaction-scoped
    # now(); set distinct request times the way separate real requests would.
    older = db_session.get(ForecastRun, uuid.UUID(first))
    run = db_session.get(ForecastRun, uuid.UUID(second))
    assert run is not None and older is not None
    older.requested_at = datetime.now(tz=UTC) - timedelta(minutes=1)
    run.requested_at = datetime.now(tz=UTC)
    run.status = "completed"
    run.completed_at = datetime.now(tz=UTC)
    run.model_params = {"resolved_model": "sarima", "warning": None}
    db_session.flush()

    history = client.get(f"/metrics/{mid}/forecasts").json()
    assert [h["id"] for h in history] == [second, first]
    assert history[0]["resolved_model"] == "sarima"
    assert history[0]["status"] == "completed"


def test_metric_anomalies_endpoint(client: TestClient, db_session: Session) -> None:
    cid = _connector(client)
    mid = _metric(client, cid)
    db_session.add(
        Anomaly(
            organization_id=uuid.UUID(LOCAL_ORG_ID),
            metric_id=uuid.UUID(mid),
            detected_at=datetime.now(tz=UTC),
            actual_value=42.0,
            expected_value=10.0,
            severity="high",
        )
    )
    db_session.flush()
    anomalies = client.get(f"/metrics/{mid}/anomalies").json()
    assert len(anomalies) == 1
    assert anomalies[0]["severity"] == "high"


# ── connector delete + runs ───────────────────────────────────────────────


def test_connector_delete_cascades_and_revokes_secret(
    client: TestClient, db_session: Session, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("SECRET_FILE", str(tmp_path / "s.env"))
    from shared.settings import get_settings

    get_settings.cache_clear()

    cid = client.post(
        "/connectors",
        json={
            "connector_definition_key": "generic_rest",
            "name": "with secret",
            "ingestion_method": "pull",
            "config": {"base_url": "http://x", "value_path": "$.v"},
            "secret": "super-secret-key",
        },
    ).json()["id"]
    mid = _metric(client, cid)

    assert client.delete(f"/connectors/{cid}").status_code == 204
    assert client.get(f"/connectors/{cid}").status_code == 404
    assert client.get(f"/metrics/{mid}").status_code == 404  # cascaded

    # secret revoked from the provider's store
    content = (tmp_path / "s.env").read_text() if (tmp_path / "s.env").exists() else ""
    assert "super-secret-key" not in content
    get_settings.cache_clear()


def test_connector_runs_history(client: TestClient, db_session: Session) -> None:
    cid = _connector(client)
    for status in ("succeeded", "failed"):
        db_session.add(
            ConnectorRun(
                connector_id=uuid.UUID(cid),
                organization_id=uuid.UUID(LOCAL_ORG_ID),
                started_at=datetime.now(tz=UTC) - timedelta(minutes=1),
                finished_at=datetime.now(tz=UTC),
                status=status,
                records_ingested=1,
            )
        )
    db_session.flush()
    runs = client.get(f"/connectors/{cid}/runs").json()
    assert len(runs) == 2
    assert {r["status"] for r in runs} == {"succeeded", "failed"}
