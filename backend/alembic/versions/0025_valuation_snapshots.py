"""Add immutable valuation snapshots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


JSONVariant = sa.JSON().with_variant(JSONB(), "postgresql")

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "valuation_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_case_id", sa.Integer(), nullable=False),
        sa.Column("research_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("verification_run_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method_pack_id", sa.String(60), nullable=False),
        sa.Column("method_pack_version", sa.String(60), nullable=False),
        sa.Column("template_id", sa.String(80), nullable=False),
        sa.Column("template_version", sa.String(60), nullable=False),
        sa.Column("calculation_engine_version", sa.String(60), nullable=False),
        sa.Column("assumptions", JSONVariant, nullable=False),
        sa.Column("base_values", JSONVariant, nullable=False),
        sa.Column("deterministic_outputs", JSONVariant, nullable=False),
        sa.Column("codex_judgment", JSONVariant, nullable=False),
        sa.Column("input_manifest", JSONVariant, nullable=False),
        sa.Column("gaps", JSONVariant, nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("calculation_fingerprint", sa.String(64), nullable=False),
        sa.Column("artifact_fingerprint", sa.String(64), nullable=False),
        sa.Column("verifier_result", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_valuation_snapshot_positive_version"),
        sa.CheckConstraint(
            "status IN ('provisional', 'verified', 'rejected', 'needs-human')",
            name="ck_valuation_snapshot_status",
        ),
        sa.ForeignKeyConstraint(["research_case_id"], ["research_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_snapshot_id"], ["research_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verification_run_id"], ["verification_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_run_id", name="uq_valuation_snapshot_agent_run"),
        sa.UniqueConstraint("verification_run_id", name="uq_valuation_snapshot_verification_run"),
        sa.UniqueConstraint("research_case_id", "version", name="uq_valuation_snapshot_case_version"),
    )
    for column in (
        "research_case_id", "research_snapshot_id", "agent_run_id",
        "verification_run_id", "status", "as_of",
    ):
        op.create_index(f"ix_valuation_snapshots_{column}", "valuation_snapshots", [column])
    op.create_index(
        "ix_valuation_snapshots_case_created",
        "valuation_snapshots",
        ["research_case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("valuation_snapshots")
