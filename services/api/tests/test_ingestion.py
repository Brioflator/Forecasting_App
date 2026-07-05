"""Push (webhook) + agent (/ingest) ingress tests (plan 05 §4, doc 1 §5.3)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.constants import LOCAL_ORG_ID
from shared.db.models import Agent, DataPoint, OutboxEvent


def _push_connector(client: TestClient) -> dict:
    resp = client.post(
        "/connectors",
        json={
            "connector_definition_key": "generic_rest",
            "name": "push source",
            "ingestion_method": "push",
            "config": {"base_url": "http://unused", "value_path": "$.v"},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["webhook_token"]  # push connectors get a webhook token at create
    return body


def _metric(client: TestClient, connector_id: str, key: str = "signups_hourly") -> str:
    return client.post(
        f"/connectors/{connector_id}/metrics", json={"name": key, "key": key}
    ).json()["id"]


def _payload(n: int = 2) -> dict:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    return {
        "metric_key": "signups_hourly",
        "points": [
            {"timestamp": base.replace(hour=h).isoformat(), "value": 100.0 + h} for h in range(n)
        ],
    }


def test_webhook_ingests_points_and_writes_outbox(client: TestClient, db_session: Session) -> None:
    connector = _push_connector(client)
    metric_id = _metric(client, connector["id"])

    resp = client.post(f"/webhooks/{connector['webhook_token']}", json=_payload(3))
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 3}

    points = db_session.scalars(
        select(DataPoint).where(DataPoint.metric_id == uuid.UUID(metric_id))
    ).all()
    assert len(points) == 3
    assert all(p.source == "webhook" for p in points)

    events = db_session.scalars(
        select(OutboxEvent).where(OutboxEvent.event_type == "data_point.ingested")
    ).all()
    assert len(events) == 3


def test_webhook_redelivery_is_idempotent(client: TestClient, db_session: Session) -> None:
    connector = _push_connector(client)
    metric_id = _metric(client, connector["id"])

    client.post(f"/webhooks/{connector['webhook_token']}", json=_payload(2))
    client.post(f"/webhooks/{connector['webhook_token']}", json=_payload(2))  # redelivered

    count = db_session.scalar(
        select(func.count())
        .select_from(DataPoint)
        .where(DataPoint.metric_id == uuid.UUID(metric_id))
    )
    assert count == 2  # deduped by (metric_id, timestamp)


def test_webhook_bad_token_404(client: TestClient) -> None:
    assert client.post("/webhooks/not-a-token", json=_payload()).status_code == 404


def test_webhook_unknown_metric_key_404(client: TestClient) -> None:
    connector = _push_connector(client)
    payload = _payload()
    payload["metric_key"] = "nope"
    resp = client.post(f"/webhooks/{connector['webhook_token']}", json=payload)
    assert resp.status_code == 404


def _register_agent(db_session: Session, connector_id: str) -> str:
    raw_token = "agent-secret-token"
    db_session.add(
        Agent(
            organization_id=uuid.UUID(LOCAL_ORG_ID),
            connector_id=uuid.UUID(connector_id),
            ingestion_token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        )
    )
    db_session.flush()
    return raw_token


def test_agent_ingest_with_bearer_token(client: TestClient, db_session: Session) -> None:
    connector = _push_connector(client)
    metric_id = _metric(client, connector["id"])
    token = _register_agent(db_session, connector["id"])

    resp = client.post("/ingest", json=_payload(2), headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 2}

    points = db_session.scalars(
        select(DataPoint).where(DataPoint.metric_id == uuid.UUID(metric_id))
    ).all()
    assert all(p.source == "agent" for p in points)

    # ingest doubled as a heartbeat
    agent = db_session.scalar(select(Agent))
    assert agent is not None and agent.last_heartbeat_at is not None


def test_agent_ingest_rejects_bad_token(client: TestClient, db_session: Session) -> None:
    connector = _push_connector(client)
    _metric(client, connector["id"])
    _register_agent(db_session, connector["id"])
    resp = client.post("/ingest", json=_payload(1), headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_agent_heartbeat_endpoint(client: TestClient, db_session: Session) -> None:
    connector = _push_connector(client)
    token = _register_agent(db_session, connector["id"])
    resp = client.post("/agents/heartbeat", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    agent = db_session.scalar(select(Agent))
    assert agent is not None and agent.last_heartbeat_at is not None
