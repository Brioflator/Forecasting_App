"""Diagnostics → candidate-set routing (guide §4 step 3).

Routing is a hint with fallbacks, never a hard decision: every candidate list
includes the baseline, and every failure path downstream lands on the baseline
with an explicit low-confidence flag. Policy only — no model fitting here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ml.constants import MAX_CANDIDATES, SF_SEASON_MAX_M, TREND_MIN, seasonal_min
from ml.profile import SeriesProfile


class Route(StrEnum):
    SHORT = "short"
    INTERMITTENT = "intermittent"
    SEASONAL = "seasonal"
    NON_SEASONAL = "non_seasonal"
    # MULTI_SEASONAL (MSTL) is phase 2 — needs second-period detection first.


@dataclass(frozen=True)
class CandidateSpec:
    """A fit recipe the engine can execute and re-fit deterministically."""

    name: str  # auto_arima | auto_ets | auto_theta | croston | tsb | seasonal_naive | naive
    m: int | None = None  # seasonal period the model is built with


def route(profile: SeriesProfile) -> Route:
    if profile.is_intermittent:
        return Route.INTERMITTENT
    m = profile.seasonal_period
    if profile.n < max(TREND_MIN, seasonal_min(m) if m else 0):
        return Route.SHORT
    if m:
        return Route.SEASONAL
    return Route.NON_SEASONAL


def candidates(rte: Route, m: int | None) -> list[CandidateSpec]:
    """Candidate set for a route, baseline always last. Capped at
    MAX_CANDIDATES by construction — this is what bounds CV work."""
    if rte is Route.SHORT:
        # No CV on short series; the caller fits the baseline directly.
        specs = [CandidateSpec("seasonal_naive", m)]
    elif rte is Route.INTERMITTENT:
        specs = [
            CandidateSpec("croston"),
            CandidateSpec("tsb"),
            CandidateSpec("naive"),
        ]
    elif rte is Route.SEASONAL:
        specs = [
            CandidateSpec("auto_ets", m),
            *([CandidateSpec("auto_arima", m)] if m and m <= SF_SEASON_MAX_M else []),
            CandidateSpec("auto_theta", m),
            CandidateSpec("seasonal_naive", m),
        ]
    else:
        specs = [
            CandidateSpec("auto_ets"),
            CandidateSpec("auto_theta"),
            CandidateSpec("naive"),
        ]
    assert len(specs) <= MAX_CANDIDATES
    return specs


def baseline_of(specs: list[CandidateSpec]) -> CandidateSpec:
    """The baseline is by convention the last candidate of every route."""
    return specs[-1]
