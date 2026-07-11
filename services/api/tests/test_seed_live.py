"""Live-API seed: the new connector definitions load, and each source's history
parser turns that API's real response shape into ordered Points (network-free
via MockTransport)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.definitions import load_connector_definitions
from api.seed_live import (
    CONNECTORS_DIR,
    _coingecko_history,
    _frankfurter_history,
    _open_meteo_history,
)
from shared.db.models import ConnectorDefinition


def _client(body: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))


def test_live_connector_definitions_load(db_session: Session) -> None:
    load_connector_definitions(db_session, CONNECTORS_DIR)
    keys = {d.key for d in db_session.scalars(select(ConnectorDefinition)).all()}
    for key in ("coingecko", "open_meteo", "frankfurter"):
        assert key in keys
    cg = db_session.scalar(
        select(ConnectorDefinition).where(ConnectorDefinition.key == "coingecko")
    )
    assert cg is not None
    assert cg.supports_pull and not cg.supports_push


def test_coingecko_history_floors_to_hour() -> None:
    body = {"prices": [[1775606400000, 71975.6], [1775692800000, 71117.0]]}
    pts = _coingecko_history(_client(body))
    assert [p.value for p in pts] == [71975.6, 71117.0]
    assert all(p.timestamp.minute == 0 and p.timestamp.second == 0 for p in pts)


def test_open_meteo_history_drops_future_points() -> None:
    past = (datetime.now(tz=UTC) - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    future = (datetime.now(tz=UTC) + timedelta(hours=5)).replace(minute=0, second=0, microsecond=0)
    body = {
        "hourly": {
            "time": [past.strftime("%Y-%m-%dT%H:%M"), future.strftime("%Y-%m-%dT%H:%M")],
            "temperature_2m": [12.0, 99.0],
        }
    }
    pts = _open_meteo_history(_client(body))
    assert [p.value for p in pts] == [12.0]  # the forecast tail is excluded


def test_frankfurter_history_sorted_and_noon() -> None:
    body = {"rates": {"2026-06-16": {"EUR": 0.86}, "2026-06-15": {"EUR": 0.85}}}
    pts = _frankfurter_history(_client(body))
    assert [p.value for p in pts] == [0.85, 0.86]  # ascending by date
    assert all(p.timestamp.hour == 12 for p in pts)
