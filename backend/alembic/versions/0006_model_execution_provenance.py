"""Add idempotency and per-attempt model execution provenance.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def _add_missing(table: str, columns: dict[str, sa.Column]) -> None:
    existing = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)
    }
    for name, column in columns.items():
        if name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    _add_missing(
        "analyses",
        {
            "idempotency_key_hash": sa.Column("idempotency_key_hash", sa.String(64)),
            "heartbeat_at": sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        },
    )
    inspector = sa.inspect(op.get_bind())
    analysis_indexes = {index["name"] for index in inspector.get_indexes("analyses")}
    if "ix_analyses_idempotency_key_hash" not in analysis_indexes:
        op.create_index(
            "ix_analyses_idempotency_key_hash",
            "analyses",
            ["idempotency_key_hash"],
            unique=True,
        )

    _add_missing(
        "model_calls",
        {
            "operation_key": sa.Column("operation_key", sa.String(200)),
            "contract_name": sa.Column("contract_name", sa.String(100)),
            "contract_version": sa.Column("contract_version", sa.String(40)),
            "output": sa.Column("output", JSONVariant),
            "provider_request_id": sa.Column("provider_request_id", sa.String(200)),
            "finish_reason": sa.Column("finish_reason", sa.String(80)),
            "error_code": sa.Column("error_code", sa.String(80)),
            "cache_source_call_id": sa.Column(
                "cache_source_call_id", sa.Integer()
            ),
            "cache_hit": sa.Column(
                "cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            "billed": sa.Column("billed", sa.Boolean()),
        },
    )


def downgrade() -> None:
    # Keep conservative downgrade semantics for pilot databases with
    # out-of-band research tables. Explicit destructive cleanup can happen
    # only after RT1.3 schema reconciliation.
    pass
