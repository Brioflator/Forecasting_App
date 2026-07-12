"""Hot-path indexes for the notification bell poll and anomaly reads.

Two per-tenant read paths were doing sequential scans because Postgres does not
auto-index foreign keys:

- notifications: the bell polls unread_count every 30s per open tab
  (COUNT(*) WHERE organization_id = ? AND read_at IS NULL). A partial index on
  the unread rows stays tiny (most notifications are read) and answers the count
  directly.
- anomalies: list_metric_anomalies and the worker's per-sweep dedup lookup both
  filter metric_id and order by detected_at.

Both are pure additive indexes — no data change, safe to apply online on the
small tables this local product produces.
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX idx_notifications_unread"
        " ON notifications (organization_id) WHERE read_at IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_anomalies_metric_detected ON anomalies (metric_id, detected_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_anomalies_metric_detected")
    op.execute("DROP INDEX idx_notifications_unread")
