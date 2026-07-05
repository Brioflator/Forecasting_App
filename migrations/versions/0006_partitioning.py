"""Monthly RANGE partitioning for the high-volume tables (guide §5.3), written
at the MVP operational-basics step that turns it on (plan 05 §4).

data_points, connector_runs, and audit_log are rebuilt as declaratively
partitioned tables:
- a DEFAULT partition catches all pre-existing/old rows, so the copy-over works
  on a populated database;
- ensure_month_partitions(parent, months_ahead) creates the current + N future
  monthly partitions; the migration calls it, and the worker's daily
  maintenance job keeps calling it so a new month's partition always exists
  before the month starts (rows never fall into DEFAULT for a current month).

pg_partman (guide §5.3) is the production/Supabase automation for the same
shape; locally the plain plpgsql function keeps the compose stack extension-
free. Swapping maintenance to pg_partman later touches only the maintenance
call, not the table layout.

Partitioned-table constraint: the PK must include the partition key, so
connector_runs/audit_log PKs become (id, started_at)/(id, created_at). Nothing
FKs into these tables, so the widened PK is invisible to the rest of the schema.
data_points' natural PK (metric_id, timestamp) already qualifies — but the FK
to metrics must be re-declared on the new parent.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ENSURE_FN = """
CREATE OR REPLACE FUNCTION ensure_month_partitions(parent text, months_ahead int DEFAULT 3)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    month_start date := date_trunc('month', now())::date;
    m date;
    part_name text;
BEGIN
    FOR i IN 0..months_ahead LOOP
        m := (month_start + make_interval(months => i))::date;
        part_name := parent || '_' || to_char(m, 'YYYY_MM');
        IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = part_name) THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                part_name, parent, m, (m + interval '1 month')::date
            );
        END IF;
    END LOOP;
END;
$$;
"""


def _repartition(
    table: str,
    partition_col: str,
    create_parent_sql: str,
    post_sql: list[str],
) -> None:
    op.execute(f"ALTER TABLE {table} RENAME TO {table}_unpartitioned")
    # Old indexes/constraints keep their names on the renamed table; rename the
    # ones we want to reuse out of the way is unnecessary — new parent uses the
    # same names only where safe (Postgres auto-names differ per table).
    op.execute(create_parent_sql)
    op.execute(f"CREATE TABLE {table}_default PARTITION OF {table} DEFAULT")
    op.execute(f"SELECT ensure_month_partitions('{table}', 3)")
    op.execute(f"INSERT INTO {table} SELECT * FROM {table}_unpartitioned")
    op.execute(f"DROP TABLE {table}_unpartitioned CASCADE")
    for sql in post_sql:
        op.execute(sql)


def upgrade() -> None:
    op.execute(ENSURE_FN)

    _repartition(
        "data_points",
        "timestamp",
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
        ) PARTITION BY RANGE ("timestamp")
        """,
        post_sql=[
            # RLS re-applies to the new parent (0005 enabled it on the old one).
            "ALTER TABLE data_points ENABLE ROW LEVEL SECURITY",
            """
            CREATE POLICY org_isolation ON data_points
            FOR ALL
            USING (organization_id IN (SELECT organization_id FROM organization_members
                                       WHERE user_id = auth.uid()))
            WITH CHECK (organization_id IN (SELECT organization_id FROM organization_members
                                            WHERE user_id = auth.uid()))
            """,
        ],
    )

    _repartition(
        "connector_runs",
        "started_at",
        """
        CREATE TABLE connector_runs (
            id                UUID NOT NULL DEFAULT gen_random_uuid(),
            connector_id      UUID NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
            organization_id   UUID NOT NULL,
            started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at       TIMESTAMPTZ,
            status            TEXT NOT NULL DEFAULT 'running'
                              CHECK (status IN ('running','succeeded','failed','dead_lettered')),
            records_ingested  INTEGER DEFAULT 0,
            error_message     TEXT,
            PRIMARY KEY (id, started_at)
        ) PARTITION BY RANGE (started_at)
        """,
        post_sql=[
            "CREATE INDEX idx_connector_runs_connector ON connector_runs(connector_id, started_at)",
            "ALTER TABLE connector_runs ENABLE ROW LEVEL SECURITY",
            """
            CREATE POLICY org_isolation ON connector_runs
            FOR ALL
            USING (organization_id IN (SELECT organization_id FROM organization_members
                                       WHERE user_id = auth.uid()))
            WITH CHECK (organization_id IN (SELECT organization_id FROM organization_members
                                            WHERE user_id = auth.uid()))
            """,
        ],
    )

    _repartition(
        "audit_log",
        "created_at",
        """
        CREATE TABLE audit_log (
            id               UUID NOT NULL DEFAULT gen_random_uuid(),
            organization_id  UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            actor_user_id    UUID REFERENCES auth.users(id),
            action           TEXT NOT NULL,
            target_type      TEXT NOT NULL,
            target_id        UUID,
            metadata         JSONB NOT NULL DEFAULT '{}',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
        """,
        post_sql=[
            "ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY",
            """
            CREATE POLICY org_isolation ON audit_log
            FOR ALL
            USING (organization_id IN (SELECT organization_id FROM organization_members
                                       WHERE user_id = auth.uid()))
            WITH CHECK (organization_id IN (SELECT organization_id FROM organization_members
                                            WHERE user_id = auth.uid()))
            """,
        ],
    )


def downgrade() -> None:
    # Rebuilding the unpartitioned shape is possible but lossy to attempt
    # generically; restore from backup instead (partition → monolith rollback
    # is not a supported path, mirroring pg_partman's own guidance).
    raise NotImplementedError("0006 is not reversible; restore from backup")
