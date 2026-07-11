"""Carry explicit Discover promotion context into research cases."""
from alembic import op
import sqlalchemy as sa


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode keeps the forward chain testable on SQLite, whose ALTER TABLE
    # implementation cannot add a foreign-key constraint in place.
    with op.batch_alter_table("research_cases") as batch:
        batch.add_column(sa.Column("promotion_triage_review_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("promotion_review_price_pln", sa.Numeric(14, 4), nullable=True))
        batch.add_column(sa.Column("promotion_note", sa.String(1000), nullable=True))
        batch.add_column(sa.Column("promotion_evidence_reason", sa.String(1000), nullable=True))
        batch.add_column(sa.Column("quarterly_review_due_on", sa.Date(), nullable=True))
        batch.add_column(sa.Column("material_event_review_policy", sa.String(60), nullable=True))
        batch.create_foreign_key(
            "fk_research_cases_promotion_triage_review",
            "discovery_triage_reviews",
            ["promotion_triage_review_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_research_cases_promotion_triage_review",
            ["promotion_triage_review_id"],
        )
    op.add_column("agent_runs", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_agent_runs_available_at", "agent_runs", ["available_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_available_at", table_name="agent_runs")
    op.drop_column("agent_runs", "available_at")
    with op.batch_alter_table("research_cases") as batch:
        batch.drop_constraint("uq_research_cases_promotion_triage_review", type_="unique")
        batch.drop_constraint("fk_research_cases_promotion_triage_review", type_="foreignkey")
        batch.drop_column("material_event_review_policy")
        batch.drop_column("quarterly_review_due_on")
        batch.drop_column("promotion_evidence_reason")
        batch.drop_column("promotion_note")
        batch.drop_column("promotion_review_price_pln")
        batch.drop_column("promotion_triage_review_id")
