"""Seed connectors + metrics backed by real, free, public APIs, and backfill
each with real history so they are immediately visible and forecastable.

Unlike `seed` (which uses a synthetic signal), every point here comes from a
live source:

  - CoinGecko    Bitcoin spot price (USD), hourly
  - Open-Meteo   London temperature (deg C), hourly, strong daily seasonality
  - Frankfurter  USD to EUR exchange rate, daily

Each source is pull-only and needs no API key. The connectors keep polling live
once the worker runs (the value at poll time is appended); this script just
seeds the history so the dashboard has real data on first load. Idempotent.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from api.definitions import load_connector_definitions
from api.seed import _ensure_identity
from shared.db import session as session_mod
from shared.db.models import Connector, ConnectorDefinition, DataPoint, Metric
from shared.models import Point
from shared.settings import get_settings
from shared.tls import use_os_trust_store

CONNECTORS_DIR = Path(__file__).resolve().parents[4] / "connectors"


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _coingecko_history(client: httpx.Client) -> list[Point]:
    prices = (
        client.get(
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
            params={"vs_currency": "usd", "days": "14"},
        )
        .raise_for_status()
        .json()["prices"]
    )
    return [
        Point(timestamp=_floor_hour(datetime.fromtimestamp(ms / 1000, tz=UTC)), value=float(v))
        for ms, v in prices
    ]


def _open_meteo_history(client: httpx.Client) -> list[Point]:
    hourly = (
        client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": "51.51",
                "longitude": "-0.13",
                "hourly": "temperature_2m",
                "past_days": "16",
                "forecast_days": "1",
                "timezone": "UTC",
            },
        )
        .raise_for_status()
        .json()["hourly"]
    )
    now = datetime.now(tz=UTC)
    points: list[Point] = []
    for iso, value in zip(hourly["time"], hourly["temperature_2m"], strict=True):
        if value is None:
            continue
        ts = datetime.fromisoformat(iso).replace(tzinfo=UTC)
        if ts <= now:  # drop the forecast tail; actuals only
            points.append(Point(timestamp=ts, value=float(value)))
    return points


def _frankfurter_history(client: httpx.Client) -> list[Point]:
    end = datetime.now(tz=UTC).date()
    start = end - timedelta(days=90)
    rates = (
        client.get(
            f"https://api.frankfurter.dev/v1/{start}..{end}",
            params={"base": "USD", "symbols": "EUR"},
        )
        .raise_for_status()
        .json()["rates"]
    )
    return [
        Point(
            timestamp=datetime.fromisoformat(day).replace(hour=12, tzinfo=UTC),
            value=float(day_rates["EUR"]),
        )
        for day, day_rates in sorted(rates.items())
    ]


@dataclass(frozen=True)
class LiveSource:
    definition_key: str
    connector_name: str
    metric_name: str
    metric_key: str
    unit: str
    schedule_cron: str
    config: dict[str, str]
    history: Callable[[httpx.Client], list[Point]]
    seasonal_period: int | None = None


SOURCES: list[LiveSource] = [
    LiveSource(
        definition_key="coingecko",
        connector_name="CoinGecko (Bitcoin)",
        metric_name="Bitcoin price",
        metric_key="btc_usd",
        unit="USD",
        schedule_cron="0 * * * *",  # hourly, matching the backfill granularity
        config={
            "base_url": "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
            "value_path": "$.bitcoin.usd",
        },
        history=_coingecko_history,
    ),
    LiveSource(
        definition_key="open_meteo",
        connector_name="Open-Meteo (London)",
        metric_name="London temperature",
        metric_key="london_temp_c",
        unit="°C",
        schedule_cron="0 * * * *",  # hourly
        seasonal_period=24,  # strong daily cycle
        config={
            "base_url": "https://api.open-meteo.com/v1/forecast?latitude=51.51&longitude=-0.13&current=temperature_2m",
            "value_path": "$.current.temperature_2m",
        },
        history=_open_meteo_history,
    ),
    LiveSource(
        definition_key="frankfurter",
        connector_name="Frankfurter (USD/EUR)",
        metric_name="USD to EUR rate",
        metric_key="usd_eur",
        unit="EUR per USD",
        schedule_cron="0 12 * * *",  # daily at noon, matching backfill timestamps
        config={
            "base_url": "https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR",
            "value_path": "$.rates.EUR",
        },
        history=_frankfurter_history,
    ),
]


def _ensure_connector(session: Session, org_id: uuid.UUID, source: LiveSource) -> Connector:
    definition = session.scalar(
        select(ConnectorDefinition).where(ConnectorDefinition.key == source.definition_key)
    )
    if definition is None:
        raise RuntimeError(f"{source.definition_key} definition missing; load definitions first")
    connector = session.scalar(
        select(Connector).where(
            Connector.organization_id == org_id, Connector.name == source.connector_name
        )
    )
    if connector is None:
        connector = Connector(
            organization_id=org_id,
            connector_definition_id=definition.id,
            name=source.connector_name,
            config=source.config,
            ingestion_method="pull",
            schedule_cron=source.schedule_cron,
        )
        session.add(connector)
        session.flush()
    else:
        connector.config = source.config
        connector.schedule_cron = source.schedule_cron
        if connector.status == "error":
            connector.status = "active"
    return connector


def _ensure_metric(
    session: Session, org_id: uuid.UUID, connector: Connector, source: LiveSource
) -> Metric:
    metric = session.scalar(
        select(Metric).where(Metric.connector_id == connector.id, Metric.key == source.metric_key)
    )
    if metric is None:
        metric = Metric(
            organization_id=org_id,
            connector_id=connector.id,
            name=source.metric_name,
            key=source.metric_key,
            unit=source.unit,
            seasonal_period=source.seasonal_period,
        )
        session.add(metric)
        session.flush()
    return metric


def _backfill(session: Session, org_id: uuid.UUID, metric: Metric, points: list[Point]) -> int:
    if not points:
        return 0
    # Collapse points that share a timestamp (e.g. two CoinGecko readings that
    # floor into the same hour) — a single INSERT ... ON CONFLICT can't touch
    # the same conflict target twice. Last write wins.
    by_ts = {p.timestamp: p.value for p in points}
    rows = [
        {
            "metric_id": metric.id,
            "organization_id": org_id,
            "timestamp": ts,
            "value": value,
            "source": "backfill",
        }
        for ts, value in sorted(by_ts.items())
    ]
    stmt = pg_insert(DataPoint).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[DataPoint.metric_id, DataPoint.timestamp],
        set_={"value": stmt.excluded.value, "source": stmt.excluded.source},
    )
    session.execute(stmt)
    return len(rows)


def seed_live() -> None:
    use_os_trust_store()
    settings = get_settings()
    factory = session_mod.get_session_factory(settings)
    with factory() as session:
        load_connector_definitions(session, CONNECTORS_DIR)
        org_id = _ensure_identity(session)
        with httpx.Client(timeout=30.0) as client:
            for source in SOURCES:
                connector = _ensure_connector(session, org_id, source)
                metric = _ensure_metric(session, org_id, connector, source)
                try:
                    points = source.history(client)
                except Exception as exc:  # noqa: BLE001 — one dead source shouldn't block the rest
                    print(f"  {source.connector_name}: history fetch failed ({exc}); skipped")
                    continue
                n = _backfill(session, org_id, metric, points)
                print(f"  {source.connector_name}: {n} real points ({source.metric_key})")
        session.commit()
    print("live-API seed complete")


if __name__ == "__main__":
    seed_live()
