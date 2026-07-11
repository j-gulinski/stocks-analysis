"""Record the persisted analysis-output contract version."""
from alembic import op
import sqlalchemy as sa


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column(
            "output_contract_version",
            sa.String(40),
            nullable=False,
            server_default="legacy",
        ),
    )


def downgrade() -> None:
    op.drop_column("analysis_runs", "output_contract_version")
