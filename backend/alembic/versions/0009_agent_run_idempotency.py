"""Add a durable idempotency key for queued Codex jobs.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("idempotency_key", sa.String(160), nullable=True),
    )
    op.create_index(
        "ix_agent_runs_idempotency_key",
        "agent_runs",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_idempotency_key", table_name="agent_runs")
    op.drop_column("agent_runs", "idempotency_key")
