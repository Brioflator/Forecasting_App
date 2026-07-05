"""Extend notifications.type with 'connector_error' (MVP operational basics).

The guide's original CHECK enumerated agent_unreachable / forecast_completed /
anomaly_detected / export_ready; the doc 1 §7 failure path ("connector flips to
'error' and a notification is raised") needs its own type. Recorded as an
addendum migration per the doc 1 §12 pattern.
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TYPES_NEW = (
    "('agent_unreachable','forecast_completed','anomaly_detected','export_ready','connector_error')"
)
TYPES_OLD = "('agent_unreachable','forecast_completed','anomaly_detected','export_ready')"


def upgrade() -> None:
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_type_check")
    op.execute(
        f"ALTER TABLE notifications ADD CONSTRAINT notifications_type_check CHECK (type IN {TYPES_NEW})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'connector_error'")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_type_check")
    op.execute(
        f"ALTER TABLE notifications ADD CONSTRAINT notifications_type_check CHECK (type IN {TYPES_OLD})"
    )
