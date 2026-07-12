"""Add a typed per-method conclusion to immutable perspective artifacts.

Revision ID: 0029
Revises: 0028
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


JSONVariant = sa.JSON().with_variant(JSONB(), "postgresql")


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_method_perspectives",
        sa.Column("conclusion", JSONVariant, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("research_method_perspectives", "conclusion")
