"""Golden-file forecasts (doc 3 §7, plan 05 §2.6).

Committed JSON fixtures under tests/golden/, one file per case. The test loads
the fixture, calls forecast()/eda() in-process (no HTTP, no DB), and compares
numeric fields with pytest.approx(rel=1e-3) — a tolerance that absorbs
BLAS/library micro-differences but catches real behavioral drift. Non-numeric
fields (model, warning, frequency) are compared exactly.

Regenerate deliberately with `make regen-golden` so a human eyeballs the diff —
never a test-run auto-accept.
"""

import json
from pathlib import Path

import pytest

from ml import eda as eda_mod
from ml import forecasting
from shared.models import Point

GOLDEN_DIR = Path(__file__).parent / "golden"


def _run_forecast(request: dict) -> dict:
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
    }


def _run_eda(request: dict) -> dict:
    return eda_mod.eda(
        series=[Point(**p) for p in request["series"]],
        seasonal_period=request.get("seasonal_period"),
    )


RUNNERS = {"forecast": _run_forecast, "eda": _run_eda}


def _approx(actual, expected, path: str = "") -> None:
    if isinstance(expected, bool) or expected is None:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"
    elif isinstance(expected, (int, float)):
        assert actual == pytest.approx(expected, rel=1e-3, abs=1e-6), (
            f"{path}: {actual} != {expected}"
        )
    elif isinstance(expected, str):
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"
    elif isinstance(expected, list):
        assert len(actual) == len(expected), f"{path}: len {len(actual)} != {len(expected)}"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _approx(a, e, f"{path}[{i}]")
    elif isinstance(expected, dict):
        assert set(actual) == set(expected), f"{path}: keys {set(actual)} != {set(expected)}"
        for k in expected:
            _approx(actual[k], expected[k], f"{path}.{k}")
    else:  # pragma: no cover
        raise AssertionError(f"unhandled type at {path}: {type(expected)}")


def _golden_files() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("*.json"))


@pytest.mark.parametrize("path", _golden_files(), ids=lambda p: p.stem)
def test_golden(path: Path) -> None:
    fixture = json.loads(path.read_text())
    produced = json.loads(json.dumps(RUNNERS[fixture["kind"]](fixture["request"]), default=str))
    _approx(produced, fixture["expected"], path.stem)


def test_at_least_one_golden_of_each_kind() -> None:
    kinds = {json.loads(p.read_text())["kind"] for p in _golden_files()}
    assert {"forecast", "eda"} <= kinds
