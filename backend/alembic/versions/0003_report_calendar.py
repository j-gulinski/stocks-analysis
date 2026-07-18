"""report_calendar

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_report_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source_version_id", sa.Integer(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("report_label", sa.String(length=160), nullable=True),
        sa.Column("source_status", sa.String(length=30), nullable=False),
        sa.Column(
            "automation_status",
            sa.String(length=30),
            nullable=False,
            server_default="not-eligible",
        ),
        sa.Column("automation_reason", sa.String(length=500), nullable=True),
        sa.Column("research_agent_run_id", sa.Integer(), nullable=True),
        sa.Column("valuation_agent_run_id", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "automation_status IN ('not-eligible', 'scheduled', 'blocked', 'already-covered')",
            name="ck_company_report_schedule_automation_status",
        ),
        sa.CheckConstraint(
            "source_status IN ('scheduled', 'unavailable')",
            name="ck_company_report_schedule_source_status",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["research_agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["valuation_agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["document_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "source_version_id",
            name="uq_company_report_schedule_source_version",
        ),
    )
    op.create_index(
        "ix_company_report_schedules_company_id",
        "company_report_schedules",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_report_schedules_company_observed",
        "company_report_schedules",
        ["company_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_company_report_schedules_report_date",
        "company_report_schedules",
        ["report_date"],
        unique=False,
    )
    op.create_index(
        "ix_company_report_schedules_research_agent_run_id",
        "company_report_schedules",
        ["research_agent_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_report_schedules_source_version_id",
        "company_report_schedules",
        ["source_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_report_schedules_valuation_agent_run_id",
        "company_report_schedules",
        ["valuation_agent_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_report_schedules_valuation_agent_run_id",
        table_name="company_report_schedules",
    )
    op.drop_index(
        "ix_company_report_schedules_source_version_id",
        table_name="company_report_schedules",
    )
    op.drop_index(
        "ix_company_report_schedules_research_agent_run_id",
        table_name="company_report_schedules",
    )
    op.drop_index(
        "ix_company_report_schedules_report_date",
        table_name="company_report_schedules",
    )
    op.drop_index(
        "ix_company_report_schedules_company_observed",
        table_name="company_report_schedules",
    )
    op.drop_index(
        "ix_company_report_schedules_company_id",
        table_name="company_report_schedules",
    )
    op.drop_table("company_report_schedules")
