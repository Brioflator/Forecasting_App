"""RLS policies (guide §5.4) — written at the MVP step that turns them on
(plan 05 §4), together with the cross-org isolation tests.

Mechanism: every tenant-owned table gets `organization_id IN (member orgs of
auth.uid())`. Locally, auth.uid() doesn't exist (it's a Supabase builtin), so
this migration creates a GUC-backed shim ONLY when absent — reading
`request.jwt.claim.sub`, the same claim Supabase's real auth.uid() reads — so
the policies are byte-identical across editions.

Note: the app's own connection (table owner) bypasses RLS; these policies bite
for non-owner roles (Supabase's `authenticated`, or the `rls_probe` role the
isolation tests create). App-layer org filtering remains the first line
locally; RLS is the structural enforcement (guide §5).
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Tables with a flat organization_id column (guide §5.4 enumerates these).
ORG_SCOPED_TABLES = [
    "connectors",
    "metrics",
    "forecast_runs",
    "eda_reports",
    "export_jobs",
    "agents",
    "data_points",
    "organization_invitations",
    "subscriptions",
    "api_keys",
    "connector_runs",
    "notifications",
    "audit_log",
    "anomalies",
    "llm_interpretations",
]
# forecast_points and outbox_events are deliberately excluded (guide §5.4).


def upgrade() -> None:
    # auth.uid() shim: create only if absent (on Supabase the real one exists).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'auth' AND p.proname = 'uid'
            ) THEN
                CREATE FUNCTION auth.uid() RETURNS uuid
                LANGUAGE sql STABLE
                AS $fn$
                    SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid
                $fn$;
            END IF;
        END
        $$;
        """
    )

    # organizations: members see their own orgs.
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_members_see_their_orgs ON organizations
        FOR ALL
        USING (id IN (SELECT organization_id FROM organization_members
                      WHERE user_id = auth.uid()))
        """
    )

    # organization_members: a user sees their own membership rows. (No
    # self-referencing subquery — that would recurse through this policy.)
    op.execute("ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY members_see_own_rows ON organization_members
        FOR ALL
        USING (user_id = auth.uid())
        """
    )

    for table in ORG_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY org_isolation ON {table}
            FOR ALL
            USING (organization_id IN (SELECT organization_id FROM organization_members
                                       WHERE user_id = auth.uid()))
            WITH CHECK (organization_id IN (SELECT organization_id FROM organization_members
                                            WHERE user_id = auth.uid()))
            """
        )


def downgrade() -> None:
    for table in ORG_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS members_see_own_rows ON organization_members")
    op.execute("ALTER TABLE organization_members DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS org_members_see_their_orgs ON organizations")
    op.execute("ALTER TABLE organizations DISABLE ROW LEVEL SECURITY")
