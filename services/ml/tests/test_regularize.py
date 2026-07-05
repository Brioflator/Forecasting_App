"""Regularization tests (doc 3 §7): frequency inference + bounded gap-fill."""

from datetime import timedelta

from ml.regularize import regularize
from shared.models import Point
from shared.synthetic import demo_series

_ORIGIN = demo_series(1)[0].timestamp


def test_infers_minute_frequency() -> None:
    reg = regularize(demo_series(30, step=timedelta(minutes=1)))
    assert reg.frequency == "min"
    assert reg.impute_frac == 0.0


def test_infers_hourly_frequency() -> None:
    reg = regularize(demo_series(30, step=timedelta(hours=1)))
    assert reg.frequency == "h"


def test_small_gap_is_filled() -> None:
    pts = demo_series(20, step=timedelta(minutes=1))
    pts = [p for i, p in enumerate(pts) if i not in (8, 9)]  # a 2-gap, within the cap
    reg = regularize(pts)
    assert len(reg.series) == 20
    assert reg.impute_frac > 0
    assert not reg.series.isna().any()


def test_duplicate_timestamps_are_mean_aggregated() -> None:
    pts = demo_series(10, step=timedelta(minutes=1))
    pts.append(Point(timestamp=_ORIGIN + timedelta(minutes=3), value=999.0))
    reg = regularize(pts)
    assert not reg.series.isna().any()
    assert len(reg.series) == 10


def test_unaligned_timestamps_regularize_without_data_loss() -> None:
    """Regression (live-found): points at :12.4s past each minute — i.e. not
    aligned to the frequency boundary — must land in their buckets, not
    produce an all-NaN grid."""
    pts = [
        Point(
            timestamp=p.timestamp + timedelta(seconds=12, microseconds=400_000),
            value=p.value,
        )
        for p in demo_series(36, step=timedelta(minutes=1))
    ]
    reg = regularize(pts)
    assert reg.frequency == "min"
    assert not reg.series.isna().any()
    assert reg.impute_frac == 0.0
    assert len(reg.series) == 36


def test_large_gap_flagged_via_impute_frac() -> None:
    pts = demo_series(40, step=timedelta(minutes=1))
    pts = [p for i, p in enumerate(pts) if not (10 <= i <= 25)]  # long interior run removed
    reg = regularize(pts)
    assert reg.impute_frac > 0.05
