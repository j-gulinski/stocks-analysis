"""Add reproducible run/model-call provenance to the current analyses table.

The local pilot database may contain experimental RT.6 tables from another
worktree, including a distinct ``analysis_runs`` contract. This migration does
not overwrite or rename them. RT1.3 will reconcile those producers explicitly.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    """Add only missing pieces so pilot DB drift is preserved, not destroyed."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("analyses")}

    columns = {
        "provider": sa.Column("provider", sa.String(40)),
        "purpose": sa.Column(
            "purpose",
            sa.String(80),
            nullable=False,
            server_default="investment_verdict",
        ),
        "status": sa.Column(
            "status", sa.String(24), nullable=False, server_default="succeeded"
        ),
        "as_of": sa.Column("as_of", sa.DateTime(timezone=True)),
        "input_snapshot": sa.Column("input_snapshot", JSONVariant),
        "evidence_ids": sa.Column("evidence_ids", JSONVariant),
        "skill_version": sa.Column("skill_version", sa.String(120)),
        "skill_hash": sa.Column("skill_hash", sa.String(80)),
        "model_configuration": sa.Column("model_configuration", JSONVariant),
        "validation": sa.Column("validation", JSONVariant),
        "estimated_cost": sa.Column("estimated_cost", sa.Numeric(14, 6)),
        "latency_ms": sa.Column("latency_ms", sa.Integer()),
        "error": sa.Column("error", sa.Text()),
        "completed_at": sa.Column("completed_at", sa.DateTime(timezone=True)),
    }
    for name, column in columns.items():
        if name not in existing:
            op.add_column("analyses", column)

    inspector = sa.inspect(bind)
    index_names = {index["name"] for index in inspector.get_indexes("analyses")}
    if "ix_analyses_status" not in index_names:
        op.create_index("ix_analyses_status", "analyses", ["status"])

    op.execute(
        "UPDATE analyses SET as_of = created_at WHERE as_of IS NULL"
    )
    op.execute(
        "UPDATE analyses SET completed_at = created_at "
        "WHERE completed_at IS NULL AND status = 'succeeded'"
    )

    if "model_calls" not in inspector.get_table_names():
        op.create_table(
            "model_calls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "analysis_id",
                sa.Integer(),
                sa.ForeignKey("analyses.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(60), nullable=False),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("model", sa.String(80), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("request_hash", sa.String(80)),
            sa.Column("input_tokens", sa.Integer()),
            sa.Column("output_tokens", sa.Integer()),
            sa.Column("estimated_cost", sa.Numeric(14, 6)),
            sa.Column("latency_ms", sa.Integer()),
            sa.Column("error", sa.Text()),
            sa.Column("escalation_reason", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
        )
        op.create_index(
            "ix_model_calls_analysis_role", "model_calls", ["analysis_id", "role"]
        )


def downgrade() -> None:
    # Conservative by design: remove the table/index introduced here but keep
    # provenance columns because input_snapshot may predate this revision in a
    # pilot DB. Downgrades must never erase out-of-band research history.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "model_calls" in inspector.get_table_names():
        indexes = {index["name"] for index in inspector.get_indexes("model_calls")}
        if "ix_model_calls_analysis_role" in indexes:
            op.drop_index("ix_model_calls_analysis_role", table_name="model_calls")
        op.drop_table("model_calls")
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("analyses")}
    if "ix_analyses_status" in indexes:
        op.drop_index("ix_analyses_status", table_name="analyses")
