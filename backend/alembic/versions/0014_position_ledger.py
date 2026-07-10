"""Add read-only position context and CSV import storage.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_ledger_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("ticker", sa.String(length=12), nullable=False),
        sa.Column("instrument_name", sa.String(length=200), nullable=True),
        sa.Column("portfolio", sa.String(length=80), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("entry_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=True),
        sa.Column("size_pln", sa.Numeric(20, 2), nullable=True),
        sa.Column("sizing_rule_flag", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_ref", sa.String(length=160), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "portfolio", "source_ref", name="uq_position_ledger_source_ref"
        ),
    )
    op.create_index(
        "ix_position_ledger_entries_company_id",
        "position_ledger_entries",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_position_ledger_entries_ticker",
        "position_ledger_entries",
        ["ticker"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_ledger_entries_ticker", table_name="position_ledger_entries"
    )
    op.drop_index(
        "ix_position_ledger_entries_company_id", table_name="position_ledger_entries"
    )
    op.drop_table("position_ledger_entries")
