"""Trust surfacing for forecast runs (revalidation guide §4 steps 4+6).

`low_confidence` is the explicit "this forecast did not earn confidence" flag
(baseline not beaten, CV skipped, or fallback); `backtest` holds the full
per-candidate rolling-origin CV scores, the routing decision, the series
profile, and the deterministic re-fit config the ml service returned. JSONB
rather than a scores table: the payload is bounded (≤4 candidates × ≤3 folds)
and is only ever read whole-row alongside its run.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE forecast_runs ADD COLUMN low_confidence BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE forecast_runs ADD COLUMN backtest JSONB")
    # The anomaly sweep and any "which metrics need attention" query filter on
    # the flag per metric; the flag is rare, so a partial index stays tiny.
    op.execute(
        "CREATE INDEX idx_forecast_runs_low_confidence"
        " ON forecast_runs (metric_id) WHERE low_confidence"
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_forecast_runs_low_confidence")
    op.execute("ALTER TABLE forecast_runs DROP COLUMN backtest")
    op.execute("ALTER TABLE forecast_runs DROP COLUMN low_confidence")
