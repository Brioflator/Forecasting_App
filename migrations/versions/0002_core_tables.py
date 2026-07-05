"""Core tables (guide §5.2) + the §12.1 metrics addenda (key, seasonal_period).

Deliberate POC deviations, both pinned by plan 05 §3 step 3:
- data_points is created UNPARTITIONED here; declarative partitioning +
  pg_partman land in migration 0006 (MVP), where they can be tested properly.
- forecast_runs.model_type CHECK additionally allows 'auto' — the API's
  default request model — since the run row records what was REQUESTED; the
  model actually used is written back into model_params by the worker.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE organizations (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL,
            plan_tier   TEXT NOT NULL DEFAULT 'free'
                        CHECK (plan_tier IN ('free','pro','enterprise')),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE organization_members (
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            role            TEXT NOT NULL DEFAULT 'member'
                            CHECK (role IN ('owner','admin','member')),
            joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (organization_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE connector_definitions (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            key              TEXT NOT NULL UNIQUE,
            name             TEXT NOT NULL,
            description      TEXT,
            config_schema    JSONB NOT NULL,
            supports_push    BOOLEAN NOT NULL DEFAULT false,
            supports_pull    BOOLEAN NOT NULL DEFAULT true,
            supports_agent   BOOLEAN NOT NULL DEFAULT true,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE connectors (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            connector_definition_id  UUID NOT NULL REFERENCES connector_definitions(id),
            name                     TEXT NOT NULL,
            config                   JSONB NOT NULL DEFAULT '{}',
            secret_ref               TEXT,
            ingestion_method         TEXT NOT NULL
                                     CHECK (ingestion_method IN ('push','pull','agent')),
            schedule_cron            TEXT,
            webhook_token            TEXT UNIQUE,
            status                   TEXT NOT NULL DEFAULT 'active'
                                     CHECK (status IN ('active','paused','error')),
            created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE metrics (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id    UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            connector_id       UUID NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
            name               TEXT NOT NULL,
            key                TEXT NOT NULL,
            unit               TEXT,
            seasonal_period    INTEGER,
            extraction_config  JSONB NOT NULL DEFAULT '{}',
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_metric_key UNIQUE (connector_id, key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE data_points (
            metric_id        UUID NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
            organization_id  UUID NOT NULL,
            "timestamp"      TIMESTAMPTZ NOT NULL,
            value            DOUBLE PRECISION NOT NULL,
            source           TEXT NOT NULL DEFAULT 'poll'
                             CHECK (source IN ('poll','webhook','agent','backfill')),
            ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (metric_id, "timestamp")
        )
        """
    )
    op.execute(
        """
        CREATE TABLE forecast_runs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            metric_id       UUID NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
            model_type      TEXT NOT NULL
                            CHECK (model_type IN ('auto','sarima','ets','prophet')),
            model_params    JSONB NOT NULL DEFAULT '{}',
            horizon         INTEGER NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','running','completed','failed')),
            requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at    TIMESTAMPTZ,
            error_message   TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE forecast_points (
            forecast_run_id  UUID NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
            "timestamp"      TIMESTAMPTZ NOT NULL,
            predicted_value  DOUBLE PRECISION NOT NULL,
            lower_bound      DOUBLE PRECISION,
            upper_bound      DOUBLE PRECISION,
            PRIMARY KEY (forecast_run_id, "timestamp")
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eda_reports (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            metric_id       UUID NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
            generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            stationarity    JSONB,
            seasonality     JSONB,
            acf_pacf        JSONB
        )
        """
    )
    op.execute(
        """
        CREATE TABLE export_jobs (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            requested_by     UUID NOT NULL REFERENCES auth.users(id),
            forecast_run_id  UUID NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
            format           TEXT NOT NULL CHECK (format IN ('csv','json','xlsx')),
            status           TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending','processing','completed','failed')),
            file_path        TEXT,
            share_token      TEXT UNIQUE,
            expires_at       TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE agents (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            connector_id          UUID REFERENCES connectors(id) ON DELETE SET NULL,
            ingestion_token_hash  TEXT NOT NULL,
            last_heartbeat_at     TIMESTAMPTZ,
            status                TEXT NOT NULL DEFAULT 'active'
                                  CHECK (status IN ('active','stale','revoked')),
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at            TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX idx_connectors_org       ON connectors(organization_id)")
    op.execute("CREATE INDEX idx_metrics_org          ON metrics(organization_id)")
    op.execute("CREATE INDEX idx_metrics_connector    ON metrics(connector_id)")
    op.execute("CREATE INDEX idx_forecast_runs_metric ON forecast_runs(metric_id)")
    op.execute("CREATE INDEX idx_export_jobs_org      ON export_jobs(organization_id)")


def downgrade() -> None:
    for table in (
        "agents",
        "export_jobs",
        "eda_reports",
        "forecast_points",
        "forecast_runs",
        "data_points",
        "metrics",
        "connectors",
        "connector_definitions",
        "organization_members",
        "organizations",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
