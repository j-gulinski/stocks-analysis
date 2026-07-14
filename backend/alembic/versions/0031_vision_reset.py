"""Vision reset: one sieve, drafter-owned valuations, portfolio operations.

- valuation_snapshots: drop method-pack columns (V2), add origin, allow
  human-override rows without agent/verification runs;
- drop research_method_perspectives (V2);
- market_factor_batches/rows: market-wide factor snapshot for the one sieve (V1);
- portfolio_operations: imported myfund flows for real returns (V7).

Revision ID: 0031
Revises: 0030
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

JSONVariant = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.drop_table("research_method_perspectives")

    with op.batch_alter_table("valuation_snapshots") as batch:
        batch.drop_column("method_pack_id")
        batch.drop_column("method_pack_version")
        batch.add_column(
            sa.Column("origin", sa.String(20), nullable=False, server_default="codex")
        )
        batch.alter_column("agent_run_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column(
            "verification_run_id", existing_type=sa.Integer(), nullable=True
        )

    op.create_table(
        "market_factor_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("page_document_versions", JSONVariant, nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("coverage", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "market_factor_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("market_factor_batches.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ticker", sa.String(20), nullable=False, index=True),
        sa.Column("br_slug", sa.String(120)),
        sa.Column("name", sa.String(200)),
        sa.Column("report_period", sa.String(20)),
        sa.Column("altman_grade", sa.String(8)),
        sa.Column("altman_value", sa.Float()),
        sa.Column("piotroski_f", sa.Float()),
        sa.Column("cz", sa.Float()),
        sa.Column("cz_delta_rr_pct", sa.Float()),
        sa.Column("cwk", sa.Float()),
        sa.Column("ev_ebitda", sa.Float()),
        sa.Column("roe_pct", sa.Float()),
        sa.Column("op_margin_pct", sa.Float()),
        sa.Column("op_margin_delta_pp", sa.Float()),
        sa.Column("net_margin_pct", sa.Float()),
        sa.Column("revenue_dyn_rr_pct", sa.Float()),
        sa.Column("net_income_dyn_rr_pct", sa.Float()),
        sa.Column("debt_to_equity", sa.Float()),
        sa.Column("net_debt_ebitda", sa.Float()),
        sa.Column("net_income_ttm_pln_thousands", sa.Float()),
        sa.Column("equity_pln_thousands", sa.Float()),
        sa.Column("turnover_present", sa.Boolean()),
        sa.Column("extras", JSONVariant, nullable=False),
        sa.UniqueConstraint("batch_id", "ticker", name="uq_market_factor_row_batch_ticker"),
    )
    op.create_index(
        "ix_market_factor_rows_batch_ticker", "market_factor_rows", ["batch_id", "ticker"]
    )

    op.create_table(
        "portfolio_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False, index=True),
        sa.Column("instrument_name", sa.String(240)),
        sa.Column("ticker", sa.String(20), index=True),
        sa.Column("quantity", sa.Float()),
        sa.Column("price", sa.Float()),
        sa.Column("amount_pln", sa.Float()),
        sa.Column("currency", sa.String(10), nullable=False, server_default="PLN"),
        sa.Column("source", sa.String(20), nullable=False, server_default="api"),
        sa.Column("provider_key", sa.String(120)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("raw", JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "portfolio_id", "content_hash", name="uq_portfolio_operation_content"
        ),
    )
    op.create_index(
        "ix_portfolio_operations_portfolio_date",
        "portfolio_operations",
        ["portfolio_id", "occurred_on"],
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration (disposable local DB).")
