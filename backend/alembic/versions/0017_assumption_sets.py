"""Add case-linked scenario assumption sets with provenance."""
from alembic import op
import sqlalchemy as sa


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assumption_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "research_case_id",
            sa.Integer(),
            sa.ForeignKey("research_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scenario_kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True)),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "research_case_id", "scenario_kind",
            name="uq_assumption_set_case_scenario",
        ),
    )
    op.create_index(
        "ix_assumption_sets_research_case_id",
        "assumption_sets",
        ["research_case_id"],
    )
    op.create_index(
        "ix_assumption_sets_status",
        "assumption_sets",
        ["status"],
    )
    op.create_index(
        "ix_assumption_sets_case_status",
        "assumption_sets",
        ["research_case_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_assumption_sets_case_status", table_name="assumption_sets")
    op.drop_index("ix_assumption_sets_status", table_name="assumption_sets")
    op.drop_index("ix_assumption_sets_research_case_id", table_name="assumption_sets")
    op.drop_table("assumption_sets")
