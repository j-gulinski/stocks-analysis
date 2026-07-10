"""Add durable list-source poll watermarks.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "list_poll_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_target_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_next_offset", sa.Integer(), nullable=True),
        sa.Column("scan_next_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_list_poll_states_source_key",
        "list_poll_states",
        ["source_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_list_poll_states_source_key", table_name="list_poll_states")
    op.drop_table("list_poll_states")
