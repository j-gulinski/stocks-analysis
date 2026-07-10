"""Add the append-only investor decision journal.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "decision_journal_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("invalidation", sa.Text(), nullable=False),
        sa.Column("next_check", sa.Text(), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=False),
        sa.Column("thesis_snapshot", JSONVariant, nullable=False),
        sa.Column("thesis_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_decision_journal_entries_company_id",
        "decision_journal_entries",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_decision_journal_company_created",
        "decision_journal_entries",
        ["company_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_decision_journal_company_created",
        table_name="decision_journal_entries",
    )
    op.drop_index(
        "ix_decision_journal_entries_company_id",
        table_name="decision_journal_entries",
    )
    op.drop_table("decision_journal_entries")
