"""Add companies.br_slug — BiznesRadar canonical slug (SNT → SYNEKTIK).

Ticker report-URLs redirect to the slug and DROP the ,Q/,Y suffix, silently
serving the annual view; report pages must therefore be fetched by slug.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("br_slug", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "br_slug")
