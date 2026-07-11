"""Add immutable company profiles and research snapshots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


JSONVariant = sa.JSON().with_variant(JSONB(), "postgresql")


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_case_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("archetype", sa.String(40), nullable=False),
        sa.Column("archetype_version", sa.String(40), nullable=False),
        sa.Column("company_overlay", JSONVariant, nullable=False),
        sa.Column("drivers", JSONVariant, nullable=False),
        sa.Column("kpis", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_company_profile_positive_version"),
        sa.ForeignKeyConstraint(["research_case_id"], ["research_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_case_id", "version", name="uq_company_profile_case_version"),
    )
    op.create_index("ix_company_profiles_research_case_id", "company_profiles", ["research_case_id"])
    op.create_index("ix_company_profiles_archetype", "company_profiles", ["archetype"])

    op.create_table(
        "research_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_case_id", sa.Integer(), nullable=False),
        sa.Column("company_profile_id", sa.Integer(), nullable=False),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("verification_run_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_fingerprint", sa.String(128), nullable=False),
        sa.Column("artifact_fingerprint", sa.String(64), nullable=False),
        sa.Column("sections", JSONVariant, nullable=False),
        sa.Column("source_manifest", JSONVariant, nullable=False),
        sa.Column("conflicts", JSONVariant, nullable=False),
        sa.Column("gaps", JSONVariant, nullable=False),
        sa.Column("next_checks", JSONVariant, nullable=False),
        sa.Column("statement_provenance", JSONVariant, nullable=False),
        sa.Column("verifier_result", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_research_snapshot_positive_version"),
        sa.CheckConstraint(
            "status IN ('provisional', 'verified', 'rejected', 'needs-human')",
            name="ck_research_snapshot_status",
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verification_run_id"], ["verification_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_profile_id"], ["company_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["research_case_id"], ["research_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_run_id", name="uq_research_snapshot_agent_run"),
        sa.UniqueConstraint("verification_run_id", name="uq_research_snapshot_verification_run"),
        sa.UniqueConstraint("research_case_id", "version", name="uq_research_snapshot_case_version"),
    )
    op.create_index("ix_research_snapshots_agent_run_id", "research_snapshots", ["agent_run_id"])
    op.create_index("ix_research_snapshots_company_profile_id", "research_snapshots", ["company_profile_id"])
    op.create_index("ix_research_snapshots_verification_run_id", "research_snapshots", ["verification_run_id"])
    op.create_index("ix_research_snapshots_research_case_id", "research_snapshots", ["research_case_id"])
    op.create_index("ix_research_snapshots_status", "research_snapshots", ["status"])
    op.create_index("ix_research_snapshots_as_of", "research_snapshots", ["as_of"])
    op.create_index("ix_research_snapshots_case_created", "research_snapshots", ["research_case_id", "created_at"])


def downgrade() -> None:
    op.drop_table("research_snapshots")
    op.drop_table("company_profiles")
