"""Team, billing, and operational tables (guide §5.5).

connector_runs and audit_log are created UNPARTITIONED for the POC —
partitioning is migration 0006 (MVP), same deferral as data_points in 0002.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE organization_invitations (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            email            TEXT NOT NULL,
            role             TEXT NOT NULL DEFAULT 'member'
                             CHECK (role IN ('owner','admin','member')),
            invited_by       UUID NOT NULL REFERENCES auth.users(id),
            token            TEXT NOT NULL UNIQUE,
            status           TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending','accepted','revoked','expired')),
            expires_at       TIMESTAMPTZ NOT NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE subscriptions (
            id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id           UUID NOT NULL UNIQUE
                                      REFERENCES organizations(id) ON DELETE CASCADE,
            provider                  TEXT NOT NULL DEFAULT 'stripe',
            provider_customer_id      TEXT,
            provider_subscription_id  TEXT,
            plan_tier                 TEXT NOT NULL DEFAULT 'free'
                                      CHECK (plan_tier IN ('free','pro','enterprise')),
            status                    TEXT NOT NULL DEFAULT 'active'
                                      CHECK (status IN ('active','past_due','canceled','trialing')),
            current_period_end        TIMESTAMPTZ,
            created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE api_keys (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            key_hash         TEXT NOT NULL,
            scopes           TEXT[] NOT NULL DEFAULT '{read}',
            created_by       UUID NOT NULL REFERENCES auth.users(id),
            last_used_at     TIMESTAMPTZ,
            revoked_at       TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE connector_runs (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            connector_id      UUID NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
            organization_id   UUID NOT NULL,
            started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at       TIMESTAMPTZ,
            status            TEXT NOT NULL DEFAULT 'running'
                              CHECK (status IN ('running','succeeded','failed','dead_lettered')),
            records_ingested  INTEGER DEFAULT 0,
            error_message     TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE notifications (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id          UUID REFERENCES auth.users(id),
            type             TEXT NOT NULL CHECK (type IN
                             ('agent_unreachable','forecast_completed','anomaly_detected','export_ready')),
            payload          JSONB NOT NULL DEFAULT '{}',
            read_at          TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit_log (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            actor_user_id    UUID REFERENCES auth.users(id),
            action           TEXT NOT NULL,
            target_type      TEXT NOT NULL,
            target_id        UUID,
            metadata         JSONB NOT NULL DEFAULT '{}',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_connector_runs_connector ON connector_runs(connector_id, started_at)"
    )


def downgrade() -> None:
    for table in (
        "audit_log",
        "notifications",
        "connector_runs",
        "api_keys",
        "subscriptions",
        "organization_invitations",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
