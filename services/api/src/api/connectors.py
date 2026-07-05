"""Connector-definition catalog + connector CRUD (doc 1 §5.2)."""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, HTTPException
from jsonschema import Draft7Validator
from sqlalchemy import select

from api.deps import DbDep, PrincipalDep
from api.schemas import (
    ConnectorCreate,
    ConnectorDefinitionOut,
    ConnectorOut,
    ConnectorUpdate,
)
from shared.db.models import Connector, ConnectorDefinition

router = APIRouter(tags=["connectors"])


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

    # Validate submitted config against the definition's JSON Schema — the same
    # schema that drives the wizard form (doc 4 §6).
    errors = sorted(
        Draft7Validator(definition.config_schema).iter_errors(body.config),
        key=lambda e: list(e.path),
    )
    if errors:
        raise HTTPException(422, f"invalid connector config: {errors[0].message}")

    if body.ingestion_method not in ("push", "pull", "agent"):
        raise HTTPException(422, "ingestion_method must be push|pull|agent")

    connector = Connector(
        organization_id=uuid.UUID(principal.org_id),
        connector_definition_id=definition.id,
        name=body.name,
        config=body.config,
        ingestion_method=body.ingestion_method,
        schedule_cron=body.schedule_cron,
        webhook_token=secrets.token_urlsafe(24) if body.ingestion_method == "push" else None,
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


def _get_owned(db: DbDep, principal: PrincipalDep, connector_id: uuid.UUID) -> Connector:
    connector = db.scalar(
        select(Connector).where(
            Connector.id == connector_id,
            Connector.organization_id == uuid.UUID(principal.org_id),
        )
    )
    if connector is None:
        raise HTTPException(404, "connector not found")
    return connector


@router.get("/connectors/{connector_id}", response_model=ConnectorOut)
def get_connector(connector_id: uuid.UUID, db: DbDep, principal: PrincipalDep) -> ConnectorOut:
    return _to_out(_get_owned(db, principal, connector_id))


@router.patch("/connectors/{connector_id}", response_model=ConnectorOut)
def update_connector(
    connector_id: uuid.UUID, body: ConnectorUpdate, db: DbDep, principal: PrincipalDep
) -> ConnectorOut:
    connector = _get_owned(db, principal, connector_id)
    if body.name is not None:
        connector.name = body.name
    if body.config is not None:
        connector.config = body.config
    if body.schedule_cron is not None:
        connector.schedule_cron = body.schedule_cron
    if body.status is not None:
        if body.status not in ("active", "paused", "error"):
            raise HTTPException(422, "status must be active|paused|error")
        connector.status = body.status
    db.flush()
    return _to_out(connector)
