"""Add forum_posts.upvotes (likes/thanks count, used to rank posts for AI).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("forum_posts", sa.Column("upvotes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("forum_posts", "upvotes")
