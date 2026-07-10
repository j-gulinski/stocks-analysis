"""Add append-only research-case step history."""
from alembic import op
import sqlalchemy as sa


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_case_step_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "research_case_id",
            sa.Integer(),
            sa.ForeignKey("research_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_state", sa.String(40)),
        sa.Column("from_step", sa.String(40)),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column("to_step", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_research_case_step_history_research_case_id",
        "research_case_step_history",
        ["research_case_id"],
    )
    op.create_index(
        "ix_case_step_history_case_created",
        "research_case_step_history",
        ["research_case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_step_history_case_created", table_name="research_case_step_history")
    op.drop_index(
        "ix_research_case_step_history_research_case_id",
        table_name="research_case_step_history",
    )
    op.drop_table("research_case_step_history")
