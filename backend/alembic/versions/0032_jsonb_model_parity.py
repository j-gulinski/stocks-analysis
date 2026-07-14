"""Align historical JSON columns with the PostgreSQL JSONB model contract.

Revision ID: 0032
Revises: 0031
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite's JSON type is already the model's portable representation. The
    # production PostgreSQL schema must use JSONB like every JSONVariant field.
    if op.get_bind().dialect.name != "postgresql":
        return

    columns = {
        "assumption_sets": ("assumptions",),
        "portfolio_snapshots": ("gaps",),
        "portfolio_review_snapshots": (
            "sections",
            "input_manifest",
            "gaps",
            "verifier_result",
        ),
    }
    for table_name, column_names in columns.items():
        for column_name in column_names:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.JSON(),
                type_=JSONB(),
                existing_nullable=False,
                postgresql_using=f"{column_name}::jsonb",
            )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration (disposable local DB).")
