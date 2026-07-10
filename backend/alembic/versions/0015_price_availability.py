"""Add point-in-time availability metadata to daily prices.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prices",
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_prices_scraped_at", "prices", ["scraped_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_prices_scraped_at", table_name="prices")
    op.drop_column("prices", "scraped_at")
