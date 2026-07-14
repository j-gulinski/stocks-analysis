"""Bind serving prices to immutable market-source versions.

Revision ID: 0030
Revises: 0029
"""

from alembic import op
import sqlalchemy as sa


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prices") as batch:
        batch.add_column(sa.Column("source_version_id", sa.Integer(), nullable=True))
        batch.create_index("ix_prices_source_version_id", ["source_version_id"])
        batch.create_foreign_key(
            "fk_prices_source_version_id_document_versions",
            "document_versions",
            ["source_version_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("prices") as batch:
        batch.drop_constraint(
            "fk_prices_source_version_id_document_versions", type_="foreignkey"
        )
        batch.drop_index("ix_prices_source_version_id")
        batch.drop_column("source_version_id")
