"""Agent evaluation replay storage.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agent_evaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.Integer(),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("strategy", sa.String(80), nullable=False),
        sa.Column("from_date", sa.Date()),
        sa.Column("to_date", sa.Date()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("model_role", sa.String(40)),
        sa.Column("model", sa.String(80)),
        sa.Column("parameters", JSONVariant, nullable=False),
        sa.Column("summary", JSONVariant, nullable=False),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_agent_evaluation_runs_strategy_created",
        "agent_evaluation_runs",
        ["strategy", "created_at"],
    )

    op.create_table(
        "agent_evaluation_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "evaluation_run_id",
            sa.Integer(),
            sa.ForeignKey("agent_evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analysis_run_id",
            sa.Integer(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("known_inputs", JSONVariant, nullable=False),
        sa.Column("prediction", JSONVariant, nullable=False),
        sa.Column("outcome", JSONVariant, nullable=False),
        sa.Column("score", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_agent_evaluation_observations_run_created",
        "agent_evaluation_observations",
        ["evaluation_run_id", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_table("agent_evaluation_observations")
    op.drop_table("agent_evaluation_runs")
