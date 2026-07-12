"""Replace the append-only position ledger with immutable portfolio snapshots.

Revision ID: 0026
Revises: 0025
"""

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("position_ledger_entries")
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_ref", sa.String(160), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("base_currency", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_ref", name="uq_portfolio_provider_ref"
        ),
    )
    op.create_table(
        "instrument_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_key", sa.String(200), nullable=False),
        sa.Column("provider_ticker", sa.String(80)),
        sa.Column("provider_name", sa.String(300), nullable=False),
        sa.Column("provider_type", sa.String(100)),
        sa.Column("currency", sa.String(8)),
        sa.Column("mapping_kind", sa.String(20), nullable=False),
        sa.Column("mapping_status", sa.String(20), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_key", name="uq_instrument_mapping_provider_key"
        ),
    )
    op.create_index(
        "ix_instrument_mappings_company_id", "instrument_mappings", ["company_id"]
    )
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("total_value", sa.Numeric(20, 2), nullable=False),
        sa.Column("cost_basis", sa.Numeric(20, 2)),
        sa.Column("profit", sa.Numeric(20, 2)),
        sa.Column("cash_value", sa.Numeric(20, 2)),
        sa.Column("benchmark_name", sa.String(160)),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version > 0", name="ck_portfolio_snapshot_positive_version"
        ),
        sa.UniqueConstraint(
            "portfolio_id", "version", name="uq_portfolio_snapshot_version"
        ),
    )
    op.create_index(
        "ix_portfolio_snapshots_portfolio_id", "portfolio_snapshots", ["portfolio_id"]
    )
    op.create_index("ix_portfolio_snapshots_as_of", "portfolio_snapshots", ["as_of"])
    op.create_index(
        "ix_portfolio_snapshots_input_fingerprint",
        "portfolio_snapshots",
        ["input_fingerprint"],
    )
    op.create_index(
        "ix_portfolio_snapshots_portfolio_as_of",
        "portfolio_snapshots",
        ["portfolio_id", "as_of"],
    )
    op.create_table(
        "portfolio_syncs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_snapshots.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_status_code", sa.String(30)),
        sa.Column("error", sa.String(500)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("payload_hash", sa.String(64)),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("reused_snapshot", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_portfolio_syncs_portfolio_id", "portfolio_syncs", ["portfolio_id"]
    )
    op.create_index(
        "ix_portfolio_syncs_snapshot_id", "portfolio_syncs", ["snapshot_id"]
    )
    op.create_index("ix_portfolio_syncs_status", "portfolio_syncs", ["status"])
    op.create_index(
        "ix_portfolio_syncs_payload_hash", "portfolio_syncs", ["payload_hash"]
    )
    op.create_index(
        "ix_portfolio_syncs_portfolio_requested",
        "portfolio_syncs",
        ["portfolio_id", "requested_at"],
    )
    op.create_table(
        "portfolio_position_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mapping_id",
            sa.Integer(),
            sa.ForeignKey("instrument_mappings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("mapping_kind", sa.String(20), nullable=False),
        sa.Column("mapping_status", sa.String(20), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("provider_row_key", sa.String(200), nullable=False),
        sa.Column("ticker", sa.String(80)),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("asset_type", sa.String(100)),
        sa.Column("sector", sa.String(160)),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("quote_date", sa.Date()),
        sa.Column("quote", sa.Numeric(20, 6)),
        sa.Column("quantity", sa.Numeric(24, 8)),
        sa.Column("value", sa.Numeric(20, 2), nullable=False),
        sa.Column("cost_basis", sa.Numeric(20, 2)),
        sa.Column("profit", sa.Numeric(20, 2)),
        sa.Column("allocation_pct", sa.Numeric(10, 4)),
        sa.UniqueConstraint(
            "snapshot_id", "provider_row_key", name="uq_portfolio_position_row"
        ),
    )
    op.create_index(
        "ix_portfolio_position_snapshots_snapshot_id",
        "portfolio_position_snapshots",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_portfolio_position_snapshots_mapping_id",
        "portfolio_position_snapshots",
        ["mapping_id"],
    )
    op.create_index(
        "ix_portfolio_position_snapshots_company_id",
        "portfolio_position_snapshots",
        ["company_id"],
    )
    op.create_table(
        "portfolio_value_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(20, 2)),
        sa.Column("contributed", sa.Numeric(20, 2)),
        sa.Column("profit", sa.Numeric(20, 2)),
        sa.Column("provider_return_pct", sa.Numeric(14, 6)),
        sa.Column("benchmark_return_pct", sa.Numeric(14, 6)),
        sa.Column("daily_change", sa.Numeric(20, 6)),
        sa.UniqueConstraint(
            "snapshot_id", "date", name="uq_portfolio_value_point_date"
        ),
    )
    op.create_index(
        "ix_portfolio_value_points_snapshot_id",
        "portfolio_value_points",
        ["snapshot_id"],
    )
    op.create_table(
        "portfolio_review_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "portfolio_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            sa.Integer(),
            sa.ForeignKey("agent_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "verification_run_id",
            sa.Integer(),
            sa.ForeignKey("verification_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("draft_requested_model_role", sa.String(40), nullable=False),
        sa.Column("draft_requested_model", sa.String(80), nullable=False),
        sa.Column("draft_reasoning_effort", sa.String(20), nullable=False),
        sa.Column("draft_actual_host_model", sa.String(160), nullable=False),
        sa.Column("draft_substitution_or_escalation", sa.String(1000)),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("input_manifest", sa.JSON(), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("analytics_fingerprint", sa.String(64), nullable=False),
        sa.Column("draft_fingerprint", sa.String(64), nullable=False),
        sa.Column("artifact_fingerprint", sa.String(64), nullable=False),
        sa.Column("verifier_result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_portfolio_review_positive_version"),
        sa.CheckConstraint(
            "status IN ('provisional', 'verified', 'rejected', 'needs-human')",
            name="ck_portfolio_review_status",
        ),
        sa.UniqueConstraint(
            "portfolio_id", "version", name="uq_portfolio_review_version"
        ),
        sa.UniqueConstraint("agent_run_id", name="uq_portfolio_review_agent_run"),
        sa.UniqueConstraint(
            "verification_run_id", name="uq_portfolio_review_verification_run"
        ),
    )
    op.create_index(
        "ix_portfolio_review_snapshots_portfolio_id",
        "portfolio_review_snapshots",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_portfolio_review_snapshots_portfolio_snapshot_id",
        "portfolio_review_snapshots",
        ["portfolio_snapshot_id"],
    )
    op.create_index(
        "ix_portfolio_review_snapshots_agent_run_id",
        "portfolio_review_snapshots",
        ["agent_run_id"],
    )
    op.create_index(
        "ix_portfolio_review_snapshots_verification_run_id",
        "portfolio_review_snapshots",
        ["verification_run_id"],
    )
    op.create_index(
        "ix_portfolio_review_snapshots_status", "portfolio_review_snapshots", ["status"]
    )
    op.create_index(
        "ix_portfolio_review_snapshots_as_of", "portfolio_review_snapshots", ["as_of"]
    )
    op.create_index(
        "ix_portfolio_review_portfolio_created",
        "portfolio_review_snapshots",
        ["portfolio_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("portfolio_review_snapshots")
    op.drop_table("portfolio_value_points")
    op.drop_table("portfolio_position_snapshots")
    op.drop_table("portfolio_syncs")
    op.drop_table("portfolio_snapshots")
    op.drop_table("instrument_mappings")
    op.drop_table("portfolios")
    op.create_table(
        "position_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
        ),
        sa.Column("ticker", sa.String(12), nullable=False),
        sa.Column("instrument_name", sa.String(200)),
        sa.Column("portfolio", sa.String(80), nullable=False),
        sa.Column("entry_date", sa.Date()),
        sa.Column("entry_price", sa.Numeric(14, 4)),
        sa.Column("quantity", sa.Numeric(20, 6)),
        sa.Column("size_pln", sa.Numeric(20, 2)),
        sa.Column("sizing_rule_flag", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_ref", sa.String(160), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source", "portfolio", "source_ref", name="uq_position_ledger_source_ref"
        ),
    )
