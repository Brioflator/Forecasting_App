"""`make seed` — make the guide §8 gate instant and deterministic (plan 05 §2.5).

Loads the connector catalog, the implicit org/user, a generic_rest connector
pointed at the local /dev/sample-metric endpoint, one metric
(key=sample_signups, seasonal_period=12, 1-minute cadence), and backfills ~4 full
cycles (≈48 points ending at "now", source='backfill') of the same synthetic
signal — so a real SARIMA forecast is available on the first metric-detail load,
before any live poll. Idempotent: safe to re-run.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from api.definitions import load_connector_definitions
from shared.constants import LOCAL_ORG_ID, LOCAL_ORG_NAME, LOCAL_USER_EMAIL, LOCAL_USER_ID
from shared.db import session as session_mod
from shared.db.models import AuthUser, Connector, DataPoint, Metric, Organization
from shared.settings import get_settings
from shared.synthetic import DEMO_PERIOD, sample_value

CONNECTORS_DIR = Path(__file__).resolve().parents[4] / "connectors"
BACKFILL_POINTS = 48  # ≈ 4 full cycles at m=12 → clears the 2m SARIMA floor
CONNECTOR_NAME = "Demo REST (sample signals)"
METRIC_KEY = "sample_signups"


def _ensure_identity(session: Session) -> uuid.UUID:
    org_id = uuid.UUID(LOCAL_ORG_ID)
    if session.get(AuthUser, uuid.UUID(LOCAL_USER_ID)) is None:
        session.add(AuthUser(id=uuid.UUID(LOCAL_USER_ID), email=LOCAL_USER_EMAIL))
    if session.get(Organization, org_id) is None:
        session.add(Organization(id=org_id, name=LOCAL_ORG_NAME))
    session.flush()
    return org_id


def _ensure_connector(session: Session, org_id: uuid.UUID) -> Connector:
    from shared.db.models import ConnectorDefinition

    definition = session.scalar(
        select(ConnectorDefinition).where(ConnectorDefinition.key == "generic_rest")
    )
    if definition is None:
        raise RuntimeError("generic_rest connector definition missing; load definitions first")

    connector = session.scalar(
        select(Connector).where(
            Connector.organization_id == org_id, Connector.name == CONNECTOR_NAME
        )
    )
    api_url = get_settings().api_url.rstrip("/")
    config = {
        "base_url": f"{api_url}/dev/sample-metric",
        "value_path": "$.value",
        "timestamp_path": "$.timestamp",
    }
    if connector is None:
        connector = Connector(
            organization_id=org_id,
            connector_definition_id=definition.id,
            name=CONNECTOR_NAME,
            config=config,
            ingestion_method="pull",
            schedule_cron="* * * * *",  # every minute (plan 05 §2.5)
        )
        session.add(connector)
        session.flush()
    else:
        connector.config = config
    return connector


def _ensure_metric(session: Session, org_id: uuid.UUID, connector: Connector) -> Metric:
    metric = session.scalar(
        select(Metric).where(Metric.connector_id == connector.id, Metric.key == METRIC_KEY)
    )
    if metric is None:
        metric = Metric(
            organization_id=org_id,
            connector_id=connector.id,
            name="Sample signups",
            key=METRIC_KEY,
            unit="signups",
            seasonal_period=DEMO_PERIOD,
        )
        session.add(metric)
        session.flush()
    return metric


def _backfill(session: Session, org_id: uuid.UUID, metric: Metric) -> int:
    now = datetime.now(tz=UTC).replace(second=0, microsecond=0)
    rows = [
        {
            "metric_id": metric.id,
            "organization_id": org_id,
            "timestamp": now - timedelta(minutes=(BACKFILL_POINTS - 1 - i)),
            "value": sample_value(i, m=DEMO_PERIOD),
            "source": "backfill",
        }
        for i in range(BACKFILL_POINTS)
    ]
    stmt = pg_insert(DataPoint).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[DataPoint.metric_id, DataPoint.timestamp],
        set_={"value": stmt.excluded.value, "source": stmt.excluded.source},
    )
    session.execute(stmt)
    return len(rows)


def seed() -> None:
    settings = get_settings()
    factory = session_mod.get_session_factory(settings)
    with factory() as session:
        n_defs = load_connector_definitions(session, CONNECTORS_DIR)
        org_id = _ensure_identity(session)
        connector = _ensure_connector(session, org_id)
        metric = _ensure_metric(session, org_id, connector)
        n_points = _backfill(session, org_id, metric)
        session.commit()
        print(
            f"seeded: {n_defs} connector definition(s), org={org_id}, "
            f"connector={connector.id}, metric={metric.id} ({METRIC_KEY}), "
            f"{n_points} backfill points"
        )


if __name__ == "__main__":
    seed()
