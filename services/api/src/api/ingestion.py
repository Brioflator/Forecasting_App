"""Push + agent ingestion ingress (doc 1 §5.3).

POST /webhooks/{token} — push sources; no auth header, the token in the path IS
the credential (resolved against connectors.webhook_token).
POST /ingest — agents; bearer token resolved against agents.ingestion_token_hash
(sha256 — the raw token is never stored, guide §5.2). An accepted ingest also
counts as a heartbeat.

Both converge on shared.db.ingest.upsert_points, the same path the poller uses.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from api.deps import DbDep
from shared.db.ingest import upsert_points
from shared.db.models import Agent, Connector, Metric
from shared.models import IngestPayload

router = APIRouter(tags=["ingestion"])

# Bound a single delivery: Starlette doesn't cap request bodies by default, so
# without this a misbehaving push source could stuff arbitrarily large payloads
# straight into data_points (one outbox row per point rides along).
MAX_POINTS_PER_REQUEST = 10_000


def _check_size(payload: IngestPayload) -> None:
    if len(payload.points) > MAX_POINTS_PER_REQUEST:
        raise HTTPException(413, f"too many points in one delivery (max {MAX_POINTS_PER_REQUEST})")


def _resolve_metric(db: DbDep, connector: Connector, metric_key: str) -> Metric:
    metric = db.scalar(
        select(Metric).where(Metric.connector_id == connector.id, Metric.key == metric_key)
    )
    if metric is None:
        raise HTTPException(404, f"unknown metric_key for this connector: {metric_key}")
    return metric


@router.post("/webhooks/{webhook_token}", status_code=202)
def webhook_ingress(webhook_token: str, payload: IngestPayload, db: DbDep) -> dict[str, int]:
    _check_size(payload)
    connector = db.scalar(select(Connector).where(Connector.webhook_token == webhook_token))
    if connector is None or connector.status == "paused":
        # 404 (not 401/403) so the token can't be probed apart from unknown paths.
        raise HTTPException(404, "not found")
    metric = _resolve_metric(db, connector, payload.metric_key)
    accepted = upsert_points(db, metric, payload.points, source="webhook")
    return {"accepted": accepted}


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _agent_from_bearer(db: DbDep, authorization: str | None) -> Agent:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    agent = db.scalar(select(Agent).where(Agent.ingestion_token_hash == _hash_token(token)))
    if agent is None or agent.status == "revoked":
        raise HTTPException(401, "invalid or revoked agent token")
    return agent


@router.post("/ingest", status_code=202)
def agent_ingest(
    payload: IngestPayload,
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    _check_size(payload)
    agent = _agent_from_bearer(db, authorization)
    if agent.connector_id is None:
        raise HTTPException(409, "agent is not bound to a connector")
    connector = db.get(Connector, agent.connector_id)
    if connector is None:
        raise HTTPException(409, "agent's connector no longer exists")
    metric = _resolve_metric(db, connector, payload.metric_key)

    accepted = upsert_points(db, metric, payload.points, source="agent")
    # An accepted ingest doubles as a heartbeat (guide §7.7).
    agent.last_heartbeat_at = datetime.now(tz=UTC)
    if agent.status == "stale":
        agent.status = "active"
    return {"accepted": accepted}


@router.post("/agents/heartbeat", status_code=200)
def agent_heartbeat(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    agent = _agent_from_bearer(db, authorization)
    agent.last_heartbeat_at = datetime.now(tz=UTC)
    if agent.status == "stale":
        agent.status = "active"
    return {"status": "ok"}
