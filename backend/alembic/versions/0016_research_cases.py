"""Add the durable research-case workflow root."""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("current_step", sa.String(40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True)),
        sa.Column("blocked_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "purpose", name="uq_research_case_company_purpose"
        ),
    )
    op.create_index("ix_research_cases_company_id", "research_cases", ["company_id"])
    op.create_index("ix_research_cases_state", "research_cases", ["state"])


def downgrade() -> None:
    op.drop_index("ix_research_cases_state", table_name="research_cases")
    op.drop_index("ix_research_cases_company_id", table_name="research_cases")
    op.drop_table("research_cases")
