"""Add immutable source/version/fact/event/conflict evidence ledger.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("company_ticker", sa.String(12), nullable=False),
        sa.Column("source_name", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("scope_key", sa.String(200), nullable=False),
        sa.Column("canonical_url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("period", sa.String(40)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_content_hash", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("parser_version", sa.String(120), nullable=False),
        sa.Column("last_fetch_status", sa.Integer()),
        sa.UniqueConstraint(
            "company_ticker",
            "source_name",
            "source_type",
            "scope_key",
            name="uq_source_document_identity",
        ),
    )
    op.create_index("ix_source_documents_company_id", "source_documents", ["company_id"])
    op.create_index("ix_source_documents_company_ticker", "source_documents", ["company_ticker"])
    op.create_index("ix_source_documents_source_type", "source_documents", ["source_type"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_document_id",
            sa.Integer(),
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_url", sa.String(1000), nullable=False),
        sa.Column("effective_url", sa.String(1000), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("parser_version", sa.String(120), nullable=False),
        sa.Column("parse_status", sa.String(40), nullable=False),
        sa.Column("parse_error", sa.Text()),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "source_document_id", "content_hash", name="uq_document_version_hash"
        ),
    )
    op.create_index(
        "ix_document_versions_source_document_id",
        "document_versions",
        ["source_document_id"],
    )

    op.create_table(
        "facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL")
        ),
        sa.Column("company_ticker", sa.String(12), nullable=False),
        sa.Column(
            "source_version_id",
            sa.Integer(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fact_type", sa.String(80), nullable=False),
        sa.Column("fact_key", sa.String(200), nullable=False),
        sa.Column("fact_hash", sa.String(64), nullable=False),
        sa.Column("numeric_value", sa.Numeric(24, 6)),
        sa.Column("text_value", sa.Text()),
        sa.Column("unit", sa.String(80)),
        sa.Column("period", sa.String(40)),
        sa.Column("effective_date", sa.Date()),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locator", JSONVariant, nullable=False),
        sa.Column("extractor_version", sa.String(120), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("verification_state", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_version_id", "fact_hash", name="uq_fact_version_hash"),
    )
    op.create_index("ix_facts_company_id", "facts", ["company_id"])
    op.create_index("ix_facts_company_ticker", "facts", ["company_ticker"])
    op.create_index("ix_facts_source_version_id", "facts", ["source_version_id"])
    op.create_index("ix_facts_known_at", "facts", ["known_at"])
    op.create_index("ix_facts_verification_state", "facts", ["verification_state"])
    op.create_index(
        "ix_facts_company_known_key", "facts", ["company_id", "known_at", "fact_key"]
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("company_ticker", sa.String(12), nullable=False),
        sa.Column(
            "source_version_id",
            sa.Integer(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claims", JSONVariant, nullable=False),
        sa.Column("verification_state", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_events_company_id", "events", ["company_id"])
    op.create_index("ix_events_company_ticker", "events", ["company_ticker"])
    op.create_index("ix_events_source_version_id", "events", ["source_version_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_known_at", "events", ["known_at"])

    op.create_table(
        "data_conflicts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("company_ticker", sa.String(12), nullable=False),
        sa.Column("fact_key", sa.String(200), nullable=False),
        sa.Column("period", sa.String(40)),
        sa.Column(
            "left_fact_id", sa.Integer(), sa.ForeignKey("facts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "right_fact_id", sa.Integer(), sa.ForeignKey("facts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("resolution_rule", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "left_fact_id", "right_fact_id", name="uq_data_conflict_fact_pair"
        ),
    )
    op.create_index("ix_data_conflicts_company_id", "data_conflicts", ["company_id"])
    op.create_index("ix_data_conflicts_company_ticker", "data_conflicts", ["company_ticker"])
    op.create_index("ix_data_conflicts_fact_key", "data_conflicts", ["fact_key"])
    op.create_index("ix_data_conflicts_status", "data_conflicts", ["status"])

    # Logical links are intentionally unconstrained: SQLite cannot add a
    # foreign key without table-copy migration, and facts remain authoritative.
    op.add_column("report_values", sa.Column("source_fact_id", sa.Integer()))
    op.create_index(
        "ix_report_values_source_fact_id", "report_values", ["source_fact_id"]
    )
    op.add_column("indicator_values", sa.Column("source_fact_id", sa.Integer()))
    op.create_index(
        "ix_indicator_values_source_fact_id", "indicator_values", ["source_fact_id"]
    )
    op.add_column("fetch_log", sa.Column("document_version_id", sa.Integer()))
    op.create_index(
        "ix_fetch_log_document_version_id", "fetch_log", ["document_version_id"]
    )


def downgrade() -> None:
    # Evidence is immutable audit history; do not erase it automatically.
    pass
