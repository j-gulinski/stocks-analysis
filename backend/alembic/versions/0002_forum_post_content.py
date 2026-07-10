"""Persist forum post content + AI-distilled investment expectations.

`forum_posts.content_text` was previously parsed but never stored (the
parser has always produced it — see ParsedPost.content_text — but
`forum_sync._store_posts` silently dropped it), which meant nothing fed the
forum distiller in production. `forum_intelligence.expectations` holds the
distiller's merged, upvote-weighted claims (services/forum_expectations.py)
so the AI verdict can read investor arguments instead of only the
keyword-heuristic `distilled_facts`.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("forum_posts", sa.Column("content_text", sa.Text()))
    op.add_column("forum_intelligence", sa.Column("expectations", JSONVariant))


def downgrade() -> None:
    op.drop_column("forum_intelligence", "expectations")
    op.drop_column("forum_posts", "content_text")
