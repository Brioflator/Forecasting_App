"""Row → response-model serialization shared across routers (keeps the
dependency graph one-way: routers depend on serializers, never on each other)."""

from __future__ import annotations

from api.schemas import ForecastPointOut, ForecastRunOut
from shared.db.models import ForecastRun


def run_to_out(run: ForecastRun) -> ForecastRunOut:
    warning = run.model_params.get("warning") if isinstance(run.model_params, dict) else None
    points = sorted(run.points, key=lambda p: p.timestamp)
    return ForecastRunOut(
        id=run.id,
        metric_id=run.metric_id,
        model_type=run.model_type,
        model_params=run.model_params,
        horizon=run.horizon,
        status=run.status,
        requested_at=run.requested_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        warning=warning,
        low_confidence=run.low_confidence,
        backtest=run.backtest,
        points=[
            ForecastPointOut(
                timestamp=p.timestamp,
                predicted=p.predicted_value,
                lower=p.lower_bound,
                upper=p.upper_bound,
            )
            for p in points
        ],
    )
