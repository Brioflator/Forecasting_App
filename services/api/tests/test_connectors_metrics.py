"""Connector + metric CRUD against the test DB (plan 05 §3 step 6)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_connector(client: TestClient) -> str:
    resp = client.post(
        "/connectors",
        json={
            "connector_definition_key": "generic_rest",
            "name": "demo",
            "ingestion_method": "pull",
            "schedule_cron": "* * * * *",
            "config": {"base_url": "http://api:8000/dev/sample-metric", "value_path": "$.value"},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_connector_definitions_seeded(client: TestClient) -> None:
    resp = client.get("/connector-definitions")
    assert resp.status_code == 200
    keys = {d["key"] for d in resp.json()}
    assert "generic_rest" in keys


def test_connector_crud(client: TestClient) -> None:
    cid = _create_connector(client)

    listing = client.get("/connectors").json()
    assert any(c["id"] == cid for c in listing)

    got = client.get(f"/connectors/{cid}").json()
    assert got["name"] == "demo"
    assert got["ingestion_method"] == "pull"

    patched = client.patch(f"/connectors/{cid}", json={"status": "paused"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "paused"


def test_connector_config_validated_against_schema(client: TestClient) -> None:
    # missing required value_path → 422 from JSON-Schema validation
    resp = client.post(
        "/connectors",
        json={
            "connector_definition_key": "generic_rest",
            "name": "bad",
            "ingestion_method": "pull",
            "config": {"base_url": "http://x"},
        },
    )
    assert resp.status_code == 422
    assert "value_path" in resp.text or "required" in resp.text


def test_unknown_definition_404(client: TestClient) -> None:
    resp = client.post(
        "/connectors",
        json={"connector_definition_key": "nope", "name": "x", "config": {}},
    )
    assert resp.status_code == 404


def test_metric_crud_and_uniqueness(client: TestClient) -> None:
    cid = _create_connector(client)
    resp = client.post(
        f"/connectors/{cid}/metrics",
        json={"name": "Sample signups", "key": "sample_signups", "seasonal_period": 12},
    )
    assert resp.status_code == 201, resp.text
    mid = resp.json()["id"]

    got = client.get(f"/metrics/{mid}").json()
    assert got["key"] == "sample_signups"
    assert got["seasonal_period"] == 12

    # duplicate key on same connector → 409
    dup = client.post(
        f"/connectors/{cid}/metrics",
        json={"name": "again", "key": "sample_signups"},
    )
    assert dup.status_code == 409


def test_metric_data_empty_then_present(client: TestClient, db_session) -> None:
    import uuid
    from datetime import UTC, datetime, timedelta

    from shared.constants import LOCAL_ORG_ID
    from shared.db.models import DataPoint

    cid = _create_connector(client)
    mid = client.post(f"/connectors/{cid}/metrics", json={"name": "m", "key": "k"}).json()["id"]

    empty = client.get(f"/metrics/{mid}/data").json()
    assert empty["points"] == []

    base = datetime(2026, 7, 1, tzinfo=UTC)
    for i in range(3):
        db_session.add(
            DataPoint(
                metric_id=uuid.UUID(mid),
                organization_id=uuid.UUID(LOCAL_ORG_ID),
                timestamp=base + timedelta(minutes=i),
                value=float(i),
                source="poll",
            )
        )
    db_session.flush()

    data = client.get(f"/metrics/{mid}/data").json()
    assert len(data["points"]) == 3
    assert data["points"][0]["value"] == 0.0
