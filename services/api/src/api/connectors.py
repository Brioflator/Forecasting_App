"""Connector-definition catalog + connector CRUD (doc 1 §5.2)."""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, HTTPException, Query
from jsonschema import Draft7Validator
from sqlalchemy import select

from api.deps import DbDep, OwnedConnectorDep, PrincipalDep
from api.schemas import (
    ConnectorCreate,
    ConnectorDefinitionOut,
    ConnectorOut,
    ConnectorRunOut,
    ConnectorUpdate,
)
from shared.db.models import Connector, ConnectorDefinition, ConnectorRun
from shared.domain import ConnectorStatus, IngestionMethod

router = APIRouter(tags=["connectors"])


def _validate_config(config_schema: dict, config: dict) -> None:
    """Validate submitted config against the definition's JSON Schema — the same
    schema that drives the wizard form (doc 4 §6). Raises 422 on the first error."""
    errors = sorted(
        Draft7Validator(config_schema).iter_errors(config),
        key=lambda e: list(e.path),
    )
    if errors:
        raise HTTPException(422, f"invalid connector config: {errors[0].message}")


def _to_out(c: Connector) -> ConnectorOut:
    return ConnectorOut(
        id=c.id,
        connector_definition_id=c.connector_definition_id,
        name=c.name,
        config=c.config,
        ingestion_method=c.ingestion_method,
        schedule_cron=c.schedule_cron,
        webhook_token=c.webhook_token,
        status=c.status,
    )


@router.get("/connector-definitions", response_model=list[ConnectorDefinitionOut])
def list_definitions(db: DbDep, principal: PrincipalDep) -> list[ConnectorDefinition]:
    return list(db.scalars(select(ConnectorDefinition).order_by(ConnectorDefinition.key)).all())


@router.post("/connectors", response_model=ConnectorOut, status_code=201)
def create_connector(body: ConnectorCreate, db: DbDep, principal: PrincipalDep) -> ConnectorOut:
    definition = db.scalar(
        select(ConnectorDefinition).where(ConnectorDefinition.key == body.connector_definition_key)
    )
    if definition is None:
        raise HTTPException(404, f"unknown connector definition: {body.connector_definition_key}")

    _validate_config(definition.config_schema, body.config)

    if body.ingestion_method not in IngestionMethod:
        raise HTTPException(422, f"ingestion_method must be one of {', '.join(IngestionMethod)}")

    is_push = body.ingestion_method == IngestionMethod.PUSH
    connector = Connector(
        organization_id=uuid.UUID(principal.org_id),
        connector_definition_id=definition.id,
        name=body.name,
        config=body.config,
        ingestion_method=body.ingestion_method,
        schedule_cron=body.schedule_cron,
        webhook_token=secrets.token_urlsafe(24) if is_push else None,
    )
    db.add(connector)
    db.flush()

    if body.secret:
        # Store via the SecretsProvider; only the opaque ref lands in the row.
        from shared.factory import make_secrets_provider
        from shared.settings import get_settings

        ref = f"connector_{connector.id}"
        make_secrets_provider(get_settings()).put_secret(principal.org_id, ref, body.secret)
        connector.secret_ref = ref

    return _to_out(connector)


@router.get("/connectors", response_model=list[ConnectorOut])
def list_connectors(db: DbDep, principal: PrincipalDep) -> list[ConnectorOut]:
    rows = db.scalars(
        select(Connector)
        .where(Connector.organization_id == uuid.UUID(principal.org_id))
        .order_by(Connector.created_at)
    ).all()
    return [_to_out(c) for c in rows]


@router.get("/connectors/{connector_id}", response_model=ConnectorOut)
def get_connector(connector: OwnedConnectorDep) -> ConnectorOut:
    return _to_out(connector)


@router.delete("/connectors/{connector_id}", status_code=204)
def delete_connector(connector: OwnedConnectorDep, db: DbDep) -> None:
    """Delete a connector and everything under it (metrics/points cascade).
    The stored secret is revoked first so no orphaned credential lingers in
    the SecretsProvider (guide §7.5 instant-revocation posture)."""
    if connector.secret_ref:
        from shared.factory import make_secrets_provider
        from shared.settings import get_settings

        try:
            make_secrets_provider(get_settings()).revoke_secret(
                str(connector.organization_id), connector.secret_ref
            )
        except Exception:  # noqa: BLE001 — a missing secret must not block deletion
            pass
    db.delete(connector)


@router.get("/connectors/{connector_id}/runs", response_model=list[ConnectorRunOut])
def list_connector_runs(
    connector: OwnedConnectorDep,
    db: DbDep,
    limit: int = Query(20, ge=1, le=100),
) -> list[ConnectorRunOut]:
    """Poll audit history for the connector detail screen (doc 1 §7)."""
    rows = db.scalars(
        select(ConnectorRun)
        .where(ConnectorRun.connector_id == connector.id)
        .order_by(ConnectorRun.started_at.desc())
        .limit(limit)
    ).all()
    return [
        ConnectorRunOut(
            id=r.id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            status=r.status,
            records_ingested=r.records_ingested,
            error_message=r.error_message,
        )
        for r in rows
    ]


@router.patch("/connectors/{connector_id}", response_model=ConnectorOut)
def update_connector(
    body: ConnectorUpdate, connector: OwnedConnectorDep, db: DbDep
) -> ConnectorOut:
    if body.name is not None:
        connector.name = body.name
    if body.config is not None:
        # Same JSON-Schema check as create — a PATCH must not be able to drop
        # required fields (e.g. base_url) and leave the poller to KeyError.
        definition = db.get(ConnectorDefinition, connector.connector_definition_id)
        if definition is not None:
            _validate_config(definition.config_schema, body.config)
        connector.config = body.config
    if body.schedule_cron is not None:
        connector.schedule_cron = body.schedule_cron
    if body.status is not None:
        if body.status not in ConnectorStatus:
            raise HTTPException(422, f"status must be one of {', '.join(ConnectorStatus)}")
        connector.status = body.status
    db.flush()
    return _to_out(connector)
