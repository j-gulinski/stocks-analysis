"""Database engine and session plumbing (SQLAlchemy 2.0).

Rough EF Core mapping: engine ≈ the provider/connection pool, Session ≈
DbContext (unit of work), Base ≈ the model-discovery convention.
"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base — every model in app.db.models registers itself here."""


def _create_engine():
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        # SQLite is used only in tests; FastAPI may touch it from another thread.
        kwargs["connect_args"] = {"check_same_thread": False}
        if settings.database_url in ("sqlite://", "sqlite:///:memory:"):
            # In-memory DB lives per-connection; StaticPool shares the single
            # connection so all sessions in a test see the same tables.
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    return create_engine(settings.database_url, **kwargs)


# Lazy: no connection happens until the first query.
engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding one session per request.

    Commits are explicit in service code — reads never commit accidentally.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
