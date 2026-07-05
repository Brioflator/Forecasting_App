"""Transactional outbox (guide §5.6) + anomalies / LLM interpretations (§5.7)."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE outbox_events (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            aggregate_type  TEXT NOT NULL,
            aggregate_id    TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            payload         JSONB NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            published_at    TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_outbox_unpublished ON outbox_events (created_at) WHERE published_at IS NULL"
    )
    op.execute(
        """
        CREATE TABLE anomalies (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            metric_id        UUID NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
            detected_at      TIMESTAMPTZ NOT NULL,
            actual_value     DOUBLE PRECISION NOT NULL,
            expected_value   DOUBLE PRECISION,
            severity         TEXT NOT NULL DEFAULT 'medium'
                             CHECK (severity IN ('low','medium','high')),
            method           TEXT NOT NULL DEFAULT 'residual_threshold',
            acknowledged_at  TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE llm_interpretations (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            forecast_run_id  UUID REFERENCES forecast_runs(id) ON DELETE CASCADE,
            anomaly_id       UUID REFERENCES anomalies(id) ON DELETE CASCADE,
            summary          TEXT NOT NULL,
            model            TEXT NOT NULL,
            generated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    for table in ("llm_interpretations", "anomalies", "outbox_events"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
