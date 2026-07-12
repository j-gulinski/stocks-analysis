"""Add immutable snapshot-bound Research method perspectives.

Revision ID: 0028
Revises: 0027
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


JSONVariant = sa.JSON().with_variant(JSONB(), "postgresql")


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_method_perspectives",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_case_id", sa.Integer(), nullable=False),
        sa.Column("research_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("verification_run_id", sa.Integer(), nullable=False),
        sa.Column("method_pack_id", sa.String(length=120), nullable=False),
        sa.Column("method_pack_version", sa.String(length=80), nullable=False),
        sa.Column("contract_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method_manifest", JSONVariant, nullable=False),
        sa.Column("method_manifest_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("applicability", JSONVariant, nullable=False),
        sa.Column("findings", JSONVariant, nullable=False),
        sa.Column("blind_spots", JSONVariant, nullable=False),
        sa.Column("falsifiers", JSONVariant, nullable=False),
        sa.Column("next_checks", JSONVariant, nullable=False),
        sa.Column("gaps", JSONVariant, nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("artifact_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("verifier_result", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('provisional', 'verified', 'rejected', 'needs-human')",
            name="ck_research_method_perspective_status",
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verification_run_id"], ["verification_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["research_snapshot_id"], ["research_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["research_case_id"], ["research_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_run_id", name="uq_research_method_perspective_agent_run"),
        sa.UniqueConstraint("verification_run_id", name="uq_research_method_perspective_verification_run"),
        sa.UniqueConstraint(
            "research_snapshot_id",
            "method_manifest_fingerprint",
            name="uq_research_method_perspective_snapshot_manifest",
        ),
    )
    for name, columns in (
        ("ix_research_method_perspectives_research_case_id", ["research_case_id"]),
        ("ix_research_method_perspectives_research_snapshot_id", ["research_snapshot_id"]),
        ("ix_research_method_perspectives_agent_run_id", ["agent_run_id"]),
        ("ix_research_method_perspectives_verification_run_id", ["verification_run_id"]),
        ("ix_research_method_perspectives_method_pack_id", ["method_pack_id"]),
        ("ix_research_method_perspectives_status", ["status"]),
        ("ix_research_method_perspectives_as_of", ["as_of"]),
        ("ix_research_method_perspectives_case_created", ["research_case_id", "created_at"]),
        ("ix_research_method_perspectives_snapshot_created", ["research_snapshot_id", "created_at"]),
    ):
        op.create_index(name, "research_method_perspectives", columns)


def downgrade() -> None:
    op.drop_table("research_method_perspectives")
