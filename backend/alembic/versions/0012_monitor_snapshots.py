"""Add deterministic monitor baselines and immutable change cards.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "monitor_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot", JSONVariant, nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitor_snapshots_company_id",
        "monitor_snapshots",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_monitor_snapshots_company_captured",
        "monitor_snapshots",
        ["company_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "monitor_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("from_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("to_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("changes", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitor_changes_company_id",
        "monitor_changes",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_monitor_changes_company_created",
        "monitor_changes",
        ["company_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_monitor_changes_company_created", table_name="monitor_changes"
    )
    op.drop_index("ix_monitor_changes_company_id", table_name="monitor_changes")
    op.drop_table("monitor_changes")
    op.drop_index(
        "ix_monitor_snapshots_company_captured", table_name="monitor_snapshots"
    )
    op.drop_index("ix_monitor_snapshots_company_id", table_name="monitor_snapshots")
    op.drop_table("monitor_snapshots")
