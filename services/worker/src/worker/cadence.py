"""Cadence quantization for the timestamp-absent ingest path (doc 1 §4.1).

When a source doesn't provide a timestamp, the extractor stamps the point with
`now()` quantized to the connector's cadence bucket — NOT raw `now()`. Without
this, a retried poll a few seconds later produces a different timestamp and the
(metric_id, timestamp) upsert creates a near-duplicate instead of deduping.
Quantizing restores the idempotency guarantee.
"""

from __future__ import annotations

from datetime import datetime

from croniter import croniter


def quantize_to_cadence(now: datetime, cadence: str | None) -> datetime:
    """Snap `now` down to the most recent scheduled fire of `cadence` (a cron
    expression). For '* * * * *' that's the top of the current minute; for an
    hourly cron the top of the hour — so re-polls within a bucket collapse."""
    if not cadence:
        # No cadence → floor to the minute so at least sub-minute retries dedupe.
        return now.replace(second=0, microsecond=0)
    itr = croniter(cadence, now)
    prev = itr.get_prev(datetime)
    return prev
