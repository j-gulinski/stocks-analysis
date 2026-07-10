"""Add atomic daily AI run and provider-usage ledger.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "ai_usage_daily" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "ai_usage_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("provider", sa.String(40), primary_key=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("logical_operations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("billable_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unknown_billing_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Preserve the old logical daily cap on upgrade. Detailed call/token usage
    # starts with this revision; historical runs did not retain enough attempt
    # detail to backfill it honestly.
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            INSERT INTO ai_usage_daily (
                day, provider, run_count, logical_operations, provider_attempts,
                cache_hits, billable_calls, unknown_billing_calls, input_tokens,
                output_tokens, estimated_cost, updated_at
            )
            SELECT
                (created_at AT TIME ZONE 'UTC')::date,
                '_all',
                COUNT(*), 0, 0, 0, 0, 0, 0, 0, 0, NOW()
            FROM analyses
            GROUP BY (created_at AT TIME ZONE 'UTC')::date
            ON CONFLICT (day, provider) DO NOTHING
            """
        )


def downgrade() -> None:
    # Usage history is audit data; do not erase it automatically in a pilot DB.
    pass
