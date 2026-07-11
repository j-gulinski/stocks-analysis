# Phase 0 — scaffold (backend)

## What was built
Monorepo skeleton: FastAPI app with `/api/health`, typed settings, the full DB
schema as SQLAlchemy 2.0 models, a hand-written initial Alembic migration,
docker-compose Postgres for local dev.

## Concepts worth understanding

**App factory + routers** (`app/main.py`) — FastAPI wires URL → function with
decorators; `include_router` composes route groups like mapping controller
areas in ASP.NET. There's no DI container to configure: dependencies are
declared per-parameter (`db: Session = Depends(get_db)`) and resolved per
request — `get_db` is the equivalent of a scoped `DbContext` registration.

**Settings** (`app/config.py`) — pydantic-settings reads env vars (with `.env`
fallback) into a typed class: `IOptions<Settings>` + user-secrets in one. The
`@lru_cache` accessor makes it a singleton without a container.

**Typed ORM models** (`app/db/models.py`) — `Mapped[int | None]` gives the
same "nullability lives in the type" experience as EF Core with NRT enabled.
Note the long/narrow `report_values` design: new statement lines from the
scraper never require a migration, only rows.

**Migrations** (`alembic/`) — `alembic upgrade head` ≈ `dotnet ef database
update`. The initial migration is written by hand; a test
(`tests/test_migrations.py`) asserts it matches the models exactly, so drift
is caught mechanically, not by prayer.

**Portability decision** — timestamps are set client-side in UTC (not DB
`now()`), so the identical schema runs on SQLite in tests and Postgres in
production. Watch for this trick: test-vs-prod database parity drives several
small choices (see `JSONVariant`).

## Where to look
`app/main.py` → `app/config.py` → `app/db/models.py` → `alembic/versions/0001_initial.py`.
