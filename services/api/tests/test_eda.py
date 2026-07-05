"""EDA endpoint tests: api → ml (in-process override) → eda_reports persistence."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import eda as eda_router
from shared.constants import LOCAL_ORG_ID
from shared.db.models import DataPoint, EdaReportRow
from shared.models import Point
from shared.synthetic import sample_value


class InProcessEdaClient:
    """Calls ml's eda() directly — same contract as the HTTP client."""

    def eda(self, series: list[dict], seasonal_period: int | None) -> dict:
        from ml.eda import eda

        return eda([Point(**p) for p in series], seasonal_period)


@pytest.fixture(autouse=True)
def _use_inprocess_ml() -> Iterator[None]:
    eda_router.set_eda_client(InProcessEdaClient())  # type: ignore[arg-type]
    yield
    eda_router.set_eda_client(None)


def _metric_with_data(client: TestClient, db_session: Session, n: int = 60) -> str:
    cid = client.post(
        "/connectors",
        json={
            "connector_definition_key": "generic_rest",
            "name": "demo",
            "ingestion_method": "pull",
            "config": {"base_url": "http://x", "value_path": "$.v"},
        },
    ).json()["id"]
    mid = client.post(
        f"/connectors/{cid}/metrics",
        json={"name": "m", "key": "k", "seasonal_period": 12},
    ).json()["id"]
    base = datetime(2026, 7, 1, tzinfo=UTC)
    for i in range(n):
        db_session.add(
            DataPoint(
                metric_id=uuid.UUID(mid),
                organization_id=uuid.UUID(LOCAL_ORG_ID),
                timestamp=base + timedelta(minutes=i),
                value=sample_value(i, m=12),
                source="backfill",
            )
        )
    db_session.flush()
    return mid


def test_generate_and_fetch_eda(client: TestClient, db_session: Session) -> None:
    mid = _metric_with_data(client, db_session)

    generated = client.post(f"/metrics/{mid}/eda")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    # plain-language readings pass through (doc 3 §2 — a product feature)
    assert "plain" in body["stationarity"]
    assert "plain" in body["seasonality"]
    assert body["seasonality"]["detected_period"] == 12
    assert body["acf_pacf"]["acf"][0] == 1.0

    # persisted
    count = db_session.scalar(select(func.count()).select_from(EdaReportRow))
    assert count == 1

    latest = client.get(f"/metrics/{mid}/eda")
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]


def test_eda_requires_data(client: TestClient, db_session: Session) -> None:
    mid = _metric_with_data(client, db_session, n=2)
    assert client.post(f"/metrics/{mid}/eda").status_code == 422


def test_eda_404_before_first_generate(client: TestClient, db_session: Session) -> None:
    mid = _metric_with_data(client, db_session)
    assert client.get(f"/metrics/{mid}/eda").status_code == 404
