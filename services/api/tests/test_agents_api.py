"""Agent registration / health / revocation endpoints (plan 05 §4 agent v1)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _connector(client: TestClient) -> str:
    return client.post(
        "/connectors",
        json={
            "connector_definition_key": "generic_rest",
            "name": "agent source",
            "ingestion_method": "agent",
            "config": {"base_url": "http://src", "value_path": "$.v"},
        },
    ).json()["id"]


def test_register_returns_token_once_and_compose_file(client: TestClient) -> None:
    cid = _connector(client)
    resp = client.post("/agents", json={"connector_id": cid})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    token = body["ingestion_token"]
    assert len(token) > 30
    assert token in body["compose_file"]  # pre-filled (doc 4 §2 onboarding)
    assert "FORECAST_AGENT_TOKEN" in body["compose_file"]
    assert body["agent"]["status"] == "active"

    # the token is NOT retrievable afterwards — list output has no token field
    listing = client.get("/agents").json()
    assert len(listing) == 1
    assert "ingestion_token" not in listing[0]


def test_registered_token_works_on_ingest_until_revoked(client: TestClient) -> None:
    cid = _connector(client)
    client.post(f"/connectors/{cid}/metrics", json={"name": "m", "key": "mk"})
    reg = client.post("/agents", json={"connector_id": cid}).json()
    token = reg["ingestion_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "metric_key": "mk",
        "points": [{"timestamp": "2026-07-01T00:00:00Z", "value": 1.0}],
    }

    assert client.post("/ingest", json=payload, headers=headers).status_code == 202

    revoked = client.post(f"/agents/{reg['agent']['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    # revoked token is dead
    assert client.post("/ingest", json=payload, headers=headers).status_code == 401


def test_register_unknown_connector_404(client: TestClient) -> None:
    import uuid

    resp = client.post("/agents", json={"connector_id": str(uuid.uuid4())})
    assert resp.status_code == 404
