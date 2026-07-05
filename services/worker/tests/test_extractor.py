"""Extractor + quantize_to_cadence idempotency (plan 05 §3 step 7).

The load-bearing case: a re-poll a few seconds later yields NO duplicate point,
because the timestamp-absent path quantizes now() to the cadence bucket.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db.models import DataPoint
from worker.cadence import quantize_to_cadence
from worker.extractors import GenericRestExtractor
from worker.ingest import upsert_points

_seen_headers: dict[str, str] = {}


def _mock_client(value: float) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        _seen_headers.clear()
        _seen_headers.update(request.headers)
        return httpx.Response(200, json={"value": value})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_quantize_collapses_subminute_repolls() -> None:
    t1 = datetime(2026, 7, 1, 12, 30, 5, tzinfo=UTC)
    t2 = datetime(2026, 7, 1, 12, 30, 47, tzinfo=UTC)
    assert quantize_to_cadence(t1, "* * * * *") == quantize_to_cadence(t2, "* * * * *")


def test_quantize_hourly_bucket() -> None:
    t = datetime(2026, 7, 1, 12, 30, 5, tzinfo=UTC)
    q = quantize_to_cadence(t, "0 * * * *")
    assert q == datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


def test_extractor_reads_value_and_auth_header() -> None:
    extractor = GenericRestExtractor(client=_mock_client(42.0))
    config = {
        "base_url": "http://src",
        "value_path": "$.value",
        "auth_scheme": "Bearer",
    }
    points = extractor.fetch(config, secret="tok", cadence="* * * * *")
    assert len(points) == 1
    assert points[0].value == 42.0
    assert _seen_headers.get("authorization") == "Bearer tok"


def test_repoll_produces_no_duplicate(seeded, db_session: Session) -> None:
    extractor = GenericRestExtractor(client=_mock_client(7.0))
    config = {**seeded.connector.config, "auth_scheme": "raw"}

    # Two polls a few seconds apart within the same minute bucket.
    p1 = extractor.fetch(config, secret=None, cadence="* * * * *")
    upsert_points(db_session, seeded.metric, p1, source="poll")
    db_session.flush()
    p2 = extractor.fetch(config, secret=None, cadence="* * * * *")
    upsert_points(db_session, seeded.metric, p2, source="poll")
    db_session.flush()

    count = db_session.scalar(
        select(func.count()).select_from(DataPoint).where(DataPoint.metric_id == seeded.metric.id)
    )
    assert count == 1  # deduped by (metric_id, timestamp)
