"""Record immutable CompanyProfile authorship and lineage.

Revision ID: 0027
Revises: 0026
"""

from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode keeps the forward chain testable on SQLite, whose ALTER TABLE
    # implementation cannot add a self-referential foreign-key constraint.
    with op.batch_alter_table("company_profiles") as batch:
        batch.add_column(
            sa.Column(
                "provenance",
                sa.String(length=40),
                nullable=False,
                server_default="codex-proposed",
            )
        )
        batch.add_column(
            sa.Column(
                "author",
                sa.String(length=120),
                nullable=False,
                server_default="company-research",
            )
        )
        batch.add_column(sa.Column("reason", sa.String(length=1000), nullable=True))
        batch.add_column(sa.Column("based_on_profile_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_company_profiles_based_on_profile_id",
            "company_profiles",
            ["based_on_profile_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_company_profiles_based_on_profile_id", ["based_on_profile_id"])


def downgrade() -> None:
    with op.batch_alter_table("company_profiles") as batch:
        batch.drop_index("ix_company_profiles_based_on_profile_id")
        batch.drop_constraint(
            "fk_company_profiles_based_on_profile_id", type_="foreignkey"
        )
        batch.drop_column("based_on_profile_id")
        batch.drop_column("reason")
        batch.drop_column("author")
        batch.drop_column("provenance")
