"""Add worker lease and heartbeat fields to Codex agent runs."""
from alembic import op
import sqlalchemy as sa


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("lease_owner", sa.String(160)))
    op.add_column("agent_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column("agent_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "agent_runs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_agent_runs_lease_owner", "agent_runs", ["lease_owner"])
    op.create_index("ix_agent_runs_lease_expires_at", "agent_runs", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_lease_expires_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_lease_owner", table_name="agent_runs")
    op.drop_column("agent_runs", "attempt_count")
    op.drop_column("agent_runs", "lease_expires_at")
    op.drop_column("agent_runs", "heartbeat_at")
    op.drop_column("agent_runs", "lease_owner")
