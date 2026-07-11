"""Record price-source and corporate-action adjustment status."""
from alembic import op
import sqlalchemy as sa


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prices") as batch:
        batch.add_column(sa.Column("source_name", sa.String(80)))
        batch.add_column(sa.Column("series_key", sa.String(160)))
        batch.add_column(sa.Column("basis_version", sa.String(80)))
        batch.add_column(
            sa.Column(
                "adjustment_status",
                sa.String(40),
                nullable=False,
                server_default="unknown",
            )
        )
        batch.create_index(
            "ix_prices_adjustment_status", ["adjustment_status"]
        )
        batch.create_index("ix_prices_series_key", ["series_key"])
        batch.create_check_constraint(
            "ck_prices_adjustment_status",
            "adjustment_status IN ('unknown', 'raw_unverified', 'split_adjusted', 'total_return')",
        )
        batch.create_check_constraint(
            "ck_prices_eligible_provenance",
            "adjustment_status NOT IN ('split_adjusted', 'total_return') OR "
            "(source_name IS NOT NULL AND length(trim(source_name)) > 0 AND "
            "series_key IS NOT NULL AND length(trim(series_key)) > 0 AND "
            "basis_version IS NOT NULL AND length(trim(basis_version)) > 0)",
        )


def downgrade() -> None:
    with op.batch_alter_table("prices") as batch:
        batch.drop_constraint("ck_prices_eligible_provenance", type_="check")
        batch.drop_constraint("ck_prices_adjustment_status", type_="check")
        batch.drop_index("ix_prices_series_key")
        batch.drop_index("ix_prices_adjustment_status")
        batch.drop_column("adjustment_status")
        batch.drop_column("basis_version")
        batch.drop_column("series_key")
        batch.drop_column("source_name")
