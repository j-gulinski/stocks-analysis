"""Add append-only human reviews for immutable discovery snapshots."""
from alembic import op
import sqlalchemy as sa
revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table("discovery_triage_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_document_version_id", sa.Integer(), sa.ForeignKey("document_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False), sa.Column("review_price_pln", sa.Numeric(14,4), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False), sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("next_review_date", sa.Date(), nullable=False), sa.Column("evidence_reason", sa.String(1000), nullable=False),
        sa.Column("created_by", sa.String(200)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_discovery_triage_version_ticker", "discovery_triage_reviews", ["source_document_version_id", "ticker"])
def downgrade() -> None:
    op.drop_index("ix_discovery_triage_version_ticker", table_name="discovery_triage_reviews")
    op.drop_table("discovery_triage_reviews")
