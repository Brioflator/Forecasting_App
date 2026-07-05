"""The canonical demo signal (plan 05 §2.5).

A fixed sinusoid of period 12 + seeded deterministic noise. This is real
product code: `api`'s `GET /dev/sample-metric` samples `sample_value`, and
`make seed` backfills history with `demo_series`. The ml test-suite reuses the
same generator so its fixtures match the demo the POC gate actually runs.

Deterministic and RNG-free so golden files reproduce across machines.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from shared.models import Point

DEMO_PERIOD = 12  # m: matched to the seeded metric's seasonal_period (plan 05 §2.5)
DEMO_LEVEL = 100.0
DEMO_AMPLITUDE = 10.0


def _seeded_noise(i: int, scale: float) -> float:
    """Deterministic bounded jitter from a cheap integer hash — no RNG state."""
    return scale * (((i * 2654435761) % 1000) / 1000.0 - 0.5)


def sample_value(
    i: int,
    *,
    m: int = DEMO_PERIOD,
    level: float = DEMO_LEVEL,
    amplitude: float = DEMO_AMPLITUDE,
    trend: float = 0.0,
    noise: float = 1.0,
) -> float:
    """The value at synthetic step index `i`."""
    return level + trend * i + amplitude * math.sin(2 * math.pi * i / m) + _seeded_noise(i, noise)


def demo_series(
    n: int,
    *,
    m: int = DEMO_PERIOD,
    level: float = DEMO_LEVEL,
    amplitude: float = DEMO_AMPLITUDE,
    trend: float = 0.0,
    noise: float = 1.0,
    start: datetime | None = None,
    step: timedelta = timedelta(minutes=1),
) -> list[Point]:
    """`n` points of the demo signal ending pattern, one per `step`."""
    origin = start or datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Point(
            timestamp=origin + step * i,
            value=sample_value(i, m=m, level=level, amplitude=amplitude, trend=trend, noise=noise),
        )
        for i in range(n)
    ]
