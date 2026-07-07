"""Migration ↔ model parity: `alembic upgrade head` must produce exactly the
schema the ORM models declare (the initial migration is hand-written)."""
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_alembic_upgrade_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migration_check.sqlite3'}"

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    inspector = sa.inspect(sa.create_engine(url))
    migrated_tables = set(inspector.get_table_names()) - {"alembic_version"}
    model_tables = set(Base.metadata.tables)
    assert migrated_tables == model_tables

    for table in Base.metadata.tables.values():
        migrated_columns = {c["name"] for c in inspector.get_columns(table.name)}
        model_columns = {c.name for c in table.columns}
        assert migrated_columns == model_columns, (
            f"column drift in '{table.name}': "
            f"migration={sorted(migrated_columns)} models={sorted(model_columns)}"
        )
