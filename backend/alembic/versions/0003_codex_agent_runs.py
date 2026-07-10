"""Provider-neutral Codex agent and analysis run storage.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workflow", sa.String(80), nullable=False),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("model_role", sa.String(40)),
        sa.Column("model", sa.String(80)),
        sa.Column("orchestrator_model", sa.String(80)),
        sa.Column("inputs", JSONVariant, nullable=False),
        sa.Column("outputs", JSONVariant, nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_agent_runs_status_created", "agent_runs", ["status", "created_at"]
    )
    op.create_index(
        "ix_agent_runs_workflow_created", "agent_runs", ["workflow", "created_at"]
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            sa.Integer(),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("workflow", sa.String(80), nullable=False),
        sa.Column("model_role", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("input_snapshot", JSONVariant, nullable=False),
        sa.Column("output", JSONVariant, nullable=False),
        sa.Column("verification", JSONVariant, nullable=False),
        sa.Column("alignment_score", sa.Integer()),
        sa.Column("created_by", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_analysis_runs_company_created",
        "analysis_runs",
        ["company_id", "created_at"],
    )
    op.create_index(
        "ix_analysis_runs_status_created", "analysis_runs", ["status", "created_at"]
    )

    op.create_table(
        "verification_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.Integer(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "analysis_run_id",
            sa.Integer(),
            sa.ForeignKey("analysis_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("model_role", sa.String(40), nullable=False),
        sa.Column("verifier_model", sa.String(80), nullable=False),
        sa.Column("verdict", sa.String(30), nullable=False),
        sa.Column("checks", JSONVariant, nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_verification_runs_agent_created",
        "verification_runs",
        ["agent_run_id", "created_at"],
    )
    op.create_index(
        "ix_verification_runs_analysis_created",
        "verification_runs",
        ["analysis_run_id", "created_at"],
    )

    op.create_table(
        "event_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("raw_url", sa.String(500)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("raw_text", sa.Text()),
        sa.Column("parsed", JSONVariant, nullable=False),
        sa.Column("materiality", JSONVariant, nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_event_report_source_id"),
    )
    op.create_index(
        "ix_event_reports_company_published",
        "event_reports",
        ["company_id", "published_at"],
    )

    op.create_table(
        "candidate_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "agent_run_id",
            sa.Integer(),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("workflow", sa.String(80), nullable=False),
        sa.Column("model_role", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("score", sa.Integer()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("reasons", JSONVariant, nullable=False),
        sa.Column("missing_data", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_candidate_runs_company_created",
        "candidate_runs",
        ["company_id", "created_at"],
    )
    op.create_index(
        "ix_candidate_runs_score_created", "candidate_runs", ["score", "created_at"]
    )

    op.create_table(
        "backtest_runs",
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
        "ix_backtest_runs_strategy_created",
        "backtest_runs",
        ["strategy", "created_at"],
    )

    op.create_table(
        "backtest_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "backtest_run_id",
            sa.Integer(),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
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
        sa.Column("signal", JSONVariant, nullable=False),
        sa.Column("outcome", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_backtest_observations_run_date",
        "backtest_observations",
        ["backtest_run_id", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_table("backtest_observations")
    op.drop_table("backtest_runs")
    op.drop_table("candidate_runs")
    op.drop_table("event_reports")
    op.drop_table("verification_runs")
    op.drop_table("analysis_runs")
    op.drop_table("agent_runs")
