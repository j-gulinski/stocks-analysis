"""Add companies.market_cap + enterprise_value (reported, PLN).

BiznesRadar's profile box reports the market cap directly. Deriving it as
price × shares understated it whenever the stored price or share count was
stale/misparsed — a >1 mld PLN company scored "small cap" in production.
The reported figure is now stored and preferred; derivation stays a fallback.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("market_cap", sa.Numeric(20, 0), nullable=True))
    op.add_column(
        "companies", sa.Column("enterprise_value", sa.Numeric(20, 0), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("companies", "enterprise_value")
    op.drop_column("companies", "market_cap")
