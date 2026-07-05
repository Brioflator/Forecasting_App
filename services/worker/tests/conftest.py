"""worker test fixtures: a seeded org/connector/metric against the test DB."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from shared.constants import LOCAL_ORG_ID, LOCAL_USER_ID
from shared.db.models import (
    AuthUser,
    Connector,
    ConnectorDefinition,
    Metric,
    Organization,
)


@dataclass
class Seeded:
    org_id: uuid.UUID
    connector: Connector
    metric: Metric


@pytest.fixture
def seeded(db_session: Session) -> Seeded:
    org_id = uuid.UUID(LOCAL_ORG_ID)
    db_session.add(AuthUser(id=uuid.UUID(LOCAL_USER_ID), email="local@forecast.local"))
    db_session.add(Organization(id=org_id, name="Local Organization"))
    definition = ConnectorDefinition(
        key="generic_rest", name="Generic REST", config_schema={"type": "object"}
    )
    db_session.add(definition)
    db_session.flush()
    connector = Connector(
        organization_id=org_id,
        connector_definition_id=definition.id,
        name="demo",
        ingestion_method="pull",
        schedule_cron="* * * * *",
        config={"base_url": "http://src/dev/sample-metric", "value_path": "$.value"},
    )
    db_session.add(connector)
    db_session.flush()
    metric = Metric(
        organization_id=org_id,
        connector_id=connector.id,
        name="Sample signups",
        key="sample_signups",
        seasonal_period=12,
    )
    db_session.add(metric)
    # Commit the seed so a poller rollback-on-failure can't erase it (the
    # poller shares this session in tests).
    db_session.commit()
    return Seeded(org_id=org_id, connector=connector, metric=metric)
