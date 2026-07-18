"""portfolio_auto_coverage

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_cases",
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="manual"),
    )
    with op.batch_alter_table("research_cases") as batch_op:
        batch_op.create_check_constraint(
            "ck_research_case_origin",
            "origin IN ('manual', 'discover', 'portfolio')",
        )
    op.add_column(
        "portfolio_syncs",
        sa.Column("coverage_version", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "portfolio_syncs",
        sa.Column("coverage_evaluated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "portfolio_syncs",
        sa.Column(
            "coverage_decisions",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "queue_priority",
            sa.Numeric(precision=20, scale=6),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_agent_runs_status_priority_created",
        "agent_runs",
        ["status", "queue_priority", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_status_priority_created", table_name="agent_runs")
    op.drop_column("agent_runs", "queue_priority")
    op.drop_column("portfolio_syncs", "coverage_decisions")
    op.drop_column("portfolio_syncs", "coverage_evaluated_at")
    op.drop_column("portfolio_syncs", "coverage_version")
    with op.batch_alter_table("research_cases") as batch_op:
        batch_op.drop_constraint("ck_research_case_origin", type_="check")
        batch_op.drop_column("origin")
