"""Round-trip the mapping models against the migrated schema (plan 05 §3 step 4)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.constants import LOCAL_ORG_ID, LOCAL_USER_ID
from shared.db.models import (
    AuthUser,
    Connector,
    ConnectorDefinition,
    DataPoint,
    ForecastPointRow,
    ForecastRun,
    Metric,
    Organization,
)


def _seed_org(session: Session) -> Organization:
    session.add(AuthUser(id=uuid.UUID(LOCAL_USER_ID), email="local@forecast.local"))
    org = Organization(id=uuid.UUID(LOCAL_ORG_ID), name="Local Organization")
    session.add(org)
    session.flush()
    return org


def test_full_ingest_to_forecast_roundtrip(db_session: Session) -> None:
    org = _seed_org(db_session)

    definition = ConnectorDefinition(
        key="generic_rest", name="Generic REST", config_schema={"type": "object"}
    )
    db_session.add(definition)
    db_session.flush()

    connector = Connector(
        organization_id=org.id,
        connector_definition_id=definition.id,
        name="demo",
        ingestion_method="pull",
        schedule_cron="* * * * *",
        config={"base_url": "http://example/dev/sample-metric"},
    )
    db_session.add(connector)
    db_session.flush()

    metric = Metric(
        organization_id=org.id,
        connector_id=connector.id,
        name="Sample signups",
        key="sample_signups",
        seasonal_period=12,
    )
    db_session.add(metric)
    db_session.flush()

    from datetime import UTC, datetime, timedelta

    base = datetime(2026, 7, 1, tzinfo=UTC)
    for i in range(5):
        db_session.add(
            DataPoint(
                metric_id=metric.id,
                organization_id=org.id,
                timestamp=base + timedelta(minutes=i),
                value=float(i),
                source="backfill",
            )
        )

    run = ForecastRun(
        organization_id=org.id, metric_id=metric.id, model_type="auto", horizon=12, status="pending"
    )
    db_session.add(run)
    db_session.flush()
    run.points.append(
        ForecastPointRow(
            timestamp=base + timedelta(minutes=10),
            predicted_value=5.0,
            lower_bound=4.0,
            upper_bound=6.0,
        )
    )
    db_session.commit()

    # Read everything back through fresh queries.
    fetched_metric = db_session.scalar(select(Metric).where(Metric.key == "sample_signups"))
    assert fetched_metric is not None
    assert fetched_metric.seasonal_period == 12
    assert fetched_metric.connector.definition.key == "generic_rest"

    point_count = len(
        db_session.scalars(select(DataPoint).where(DataPoint.metric_id == metric.id)).all()
    )
    assert point_count == 5

    fetched_run = db_session.scalar(select(ForecastRun).where(ForecastRun.metric_id == metric.id))
    assert fetched_run is not None
    assert len(fetched_run.points) == 1
    assert fetched_run.points[0].predicted_value == 5.0


def test_metric_key_unique_per_connector(db_session: Session) -> None:
    import pytest
    from sqlalchemy.exc import IntegrityError

    org = _seed_org(db_session)
    definition = ConnectorDefinition(key="generic_rest", name="G", config_schema={})
    db_session.add(definition)
    db_session.flush()
    connector = Connector(
        organization_id=org.id,
        connector_definition_id=definition.id,
        name="c",
        ingestion_method="pull",
    )
    db_session.add(connector)
    db_session.flush()
    db_session.add(Metric(organization_id=org.id, connector_id=connector.id, name="A", key="dup"))
    db_session.flush()
    db_session.add(Metric(organization_id=org.id, connector_id=connector.id, name="B", key="dup"))
    with pytest.raises(IntegrityError):
        db_session.flush()
