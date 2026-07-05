"""Extensions + auth.users shim (doc 1 §12.2).

IF NOT EXISTS makes the shim inert on Supabase (real auth.users already
present) and creates the minimal table locally so FKs resolve. Identical
schema both editions; no conditional FKs.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth.users (
            id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT
        )
        """
    )


def downgrade() -> None:
    # The shim is shared infrastructure on Supabase — never drop it blindly.
    pass
