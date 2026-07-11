"""Regenerate the golden fixtures (make regen-golden).

Explicit + reviewable by design (plan 05 §2.6): this rewrites the expected
outputs so a human eyeballs the git diff, rather than a test-run silently
blessing a changed forecast. Run from the repo root:

    python services/ml/tests/regen_golden.py

Imports only installed packages (shared.synthetic, ml.*) — never test modules —
so it works regardless of pytest import mode.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from ml import eda as eda_mod
from ml import forecasting
from shared.models import Point
from shared.synthetic import demo_series

GOLDEN_DIR = Path(__file__).parent / "golden"


def _series_raw(series: list[Point]) -> list[dict[str, Any]]:
    return [{"timestamp": p.timestamp.isoformat(), "value": p.value} for p in series]


def run_forecast(request: dict[str, Any]) -> dict[str, Any]:
    result = forecasting.forecast(
        series=[Point(**p) for p in request["series"]],
        horizon=request["horizon"],
        model=request.get("model", "auto"),
        seasonal_period=request.get("seasonal_period"),
        confidence=request.get("confidence", 0.95),
    )
    return {
        "model": result.model,
        "model_params": result.model_params,
        "frequency": result.frequency,
        "points": [
            {
                "timestamp": p["timestamp"].isoformat(),
                "predicted": p["predicted"],
                "lower": p["lower"],
                "upper": p["upper"],
            }
            for p in result.points
        ],
        "metrics": result.metrics,
        "warning": result.warning,
        "route": result.route,
        "low_confidence": result.low_confidence,
        "confidence_reasons": result.confidence_reasons,
        "candidates": result.candidates,
        "series_profile": result.series_profile,
        "fit_config": result.fit_config,
    }


def run_eda(request: dict[str, Any]) -> dict[str, Any]:
    return eda_mod.eda(
        series=[Point(**p) for p in request["series"]],
        seasonal_period=request.get("seasonal_period"),
    )


RUNNERS = {"forecast": run_forecast, "eda": run_eda}


def _intermittent_series(n: int) -> list[Point]:
    """Deterministic sparse-demand series: a sale every 5th day, RNG-free."""
    from datetime import UTC, datetime

    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Point(timestamp=base + timedelta(days=i), value=7.0 if i % 5 == 0 else 0.0)
        for i in range(n)
    ]


CASES: list[dict[str, Any]] = [
    {
        "name": "sarima_hourly_m12",
        "kind": "forecast",
        "request": {
            "series": _series_raw(demo_series(60, step=timedelta(hours=1))),
            "horizon": 12,
            "seasonal_period": 12,
            "confidence": 0.95,
        },
    },
    {
        "name": "intermittent_daily",
        "kind": "forecast",
        "request": {
            "series": _series_raw(_intermittent_series(60)),
            "horizon": 7,
            "seasonal_period": None,
            "confidence": 0.95,
        },
    },
    {
        "name": "trend_only_short",
        "kind": "forecast",
        "request": {
            "series": _series_raw(demo_series(15, trend=0.5)),
            "horizon": 5,
            "seasonal_period": None,
            "confidence": 0.95,
        },
    },
    {
        "name": "drift_floor",
        "kind": "forecast",
        "request": {
            "series": _series_raw(demo_series(6, trend=1.0)),
            "horizon": 3,
            "seasonal_period": None,
            "confidence": 0.9,
        },
    },
    {
        "name": "eda_seasonal_m12",
        "kind": "eda",
        "request": {
            "series": _series_raw(demo_series(72)),
            "seasonal_period": 12,
        },
    },
]


def main() -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    for case in CASES:
        expected = json.loads(json.dumps(RUNNERS[case["kind"]](case["request"]), default=str))
        fixture = {"kind": case["kind"], "request": case["request"], "expected": expected}
        out = GOLDEN_DIR / f"{case['name']}.json"
        out.write_text(json.dumps(fixture, indent=2) + "\n")
        print(f"wrote {out.name}")


if __name__ == "__main__":
    main()
