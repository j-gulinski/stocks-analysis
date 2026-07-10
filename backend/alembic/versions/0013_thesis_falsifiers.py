"""Add explicit user-managed thesis falsifiers.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thesis_falsifiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("thesis_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "key", name="uq_thesis_falsifier_company_key"
        ),
    )
    op.create_index(
        "ix_thesis_falsifiers_company_id",
        "thesis_falsifiers",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_thesis_falsifiers_status",
        "thesis_falsifiers",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_thesis_falsifiers_company_status",
        "thesis_falsifiers",
        ["company_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_thesis_falsifiers_company_status", table_name="thesis_falsifiers"
    )
    op.drop_index("ix_thesis_falsifiers_status", table_name="thesis_falsifiers")
    op.drop_index("ix_thesis_falsifiers_company_id", table_name="thesis_falsifiers")
    op.drop_table("thesis_falsifiers")
