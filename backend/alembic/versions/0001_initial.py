"""Initial schema — all tables from PLAN §4.

Revision ID: 0001
Revises:
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(12), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("market", sa.String(20)),
        sa.Column("sector", sa.String(100)),
        sa.Column("shares_outstanding", sa.BigInteger()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_companies_ticker", "companies", ["ticker"], unique=True)

    op.create_table(
        "report_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("statement", sa.String(10), nullable=False),
        sa.Column("freq", sa.String(1), nullable=False),
        sa.Column("period", sa.String(8), nullable=False),
        sa.Column("field_code", sa.String(80), nullable=False),
        sa.Column("field_label", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer()),
        sa.Column("value", sa.Numeric(20, 2)),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "statement", "freq", "period", "field_code",
            name="uq_report_value_key",
        ),
    )
    op.create_index(
        "ix_report_values_lookup", "report_values", ["company_id", "statement", "freq"]
    )

    op.create_table(
        "indicator_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("indicator", sa.String(40), nullable=False),
        sa.Column("period", sa.String(8), nullable=False),
        sa.Column("value", sa.Numeric(14, 4)),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "indicator", "period", name="uq_indicator_key"),
    )

    op.create_table(
        "dividends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("dps", sa.Numeric(10, 4)),
        sa.Column("yield_pct", sa.Numeric(6, 2)),
        sa.UniqueConstraint("company_id", "year", name="uq_dividend_year"),
    )

    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger()),
        sa.UniqueConstraint("company_id", "date", name="uq_price_day"),
    )

    op.create_table(
        "forum_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL")
        ),
        sa.Column("url", sa.String(500), nullable=False, unique=True),
        sa.Column("phpbb_topic_id", sa.Integer()),
        sa.Column("title", sa.String(300)),
        sa.Column("last_post_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_forum_topics_phpbb_topic_id", "forum_topics", ["phpbb_topic_id"])

    op.create_table(
        "forum_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("forum_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phpbb_post_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(100), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_html", sa.Text()),
        sa.UniqueConstraint("topic_id", "phpbb_post_id", name="uq_forum_post"),
    )
    op.create_index("ix_forum_posts_topic_time", "forum_posts", ["topic_id", "posted_at"])

    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("note", sa.String(500)),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(120)),
        sa.Column("assumptions", JSONVariant, nullable=False),
        sa.Column("result", JSONVariant, nullable=False),
        sa.Column("created_by", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(60), nullable=False),
        sa.Column("prescore", JSONVariant),
        sa.Column("output", JSONVariant),
        sa.Column("alignment_score", sa.Integer()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("created_by", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "fetch_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("status", sa.Integer()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fetch_log_url_at", "fetch_log", ["url", "fetched_at"])


def downgrade() -> None:
    for table in (
        "fetch_log",
        "analyses",
        "forecasts",
        "watchlist_items",
        "forum_posts",
        "forum_topics",
        "prices",
        "dividends",
        "indicator_values",
        "report_values",
        "companies",
    ):
        op.drop_table(table)
