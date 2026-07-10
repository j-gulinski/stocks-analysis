"""Atomic daily run reservation and model-usage accounting."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models import AiUsageDaily


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def reserve_run(
    db: Session, provider: str, limit: int, *, day: date | None = None
) -> bool:
    """Atomically increment run_count only while it remains below limit."""
    if limit <= 0:
        return False
    day = day or _today_utc()
    table = AiUsageDaily.__table__
    values = {
        "day": day,
        "provider": provider,
        "run_count": 1,
        "updated_at": datetime.now(timezone.utc),
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgres_insert(table).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(table).values(**values)
    else:  # pragma: no cover - supported deployments are PostgreSQL/SQLite
        raise RuntimeError(f"Unsupported quota-ledger dialect: {dialect}")
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.day, table.c.provider],
        set_={
            "run_count": table.c.run_count + 1,
            "updated_at": values["updated_at"],
        },
        where=table.c.run_count < limit,
    )
    result = db.execute(statement)
    db.commit()
    return result.rowcount == 1


def release_run(db: Session, provider: str, *, day: date | None = None) -> None:
    """Undo only a reservation lost to a concurrent idempotency-key winner."""
    day = day or _today_utc()
    db.execute(
        update(AiUsageDaily)
        .where(
            AiUsageDaily.day == day,
            AiUsageDaily.provider == provider,
            AiUsageDaily.run_count > 0,
        )
        .values(
            run_count=AiUsageDaily.run_count - 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def reserve_provider_attempt(
    db: Session,
    call_limit: int,
    token_limit: int,
    *,
    day: date | None = None,
) -> bool:
    """Reserve one global provider attempt under call and measured-token caps."""
    if call_limit <= 0 or token_limit <= 0:
        return False
    day = day or _today_utc()
    table = AiUsageDaily.__table__
    now = datetime.now(timezone.utc)
    values = {
        "day": day,
        "provider": "_all",
        "provider_attempts": 1,
        "updated_at": now,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgres_insert(table).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(table).values(**values)
    else:  # pragma: no cover
        raise RuntimeError(f"Unsupported quota-ledger dialect: {dialect}")
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.day, table.c.provider],
        set_={
            "provider_attempts": table.c.provider_attempts + 1,
            "updated_at": now,
        },
        where=(table.c.provider_attempts < call_limit)
        & ((table.c.input_tokens + table.c.output_tokens) < token_limit),
    )
    result = db.execute(statement)
    db.commit()
    return result.rowcount == 1


def record_logical_operation(db: Session, provider: str) -> None:
    _increment(db, provider, logical_operations=1)
    db.commit()


def record_cache_hit(db: Session, provider: str) -> None:
    _increment(db, provider, cache_hits=1)
    db.commit()


def record_provider_attempt(db: Session, provider: str) -> None:
    _increment(db, provider, provider_attempts=1)
    db.commit()


def record_attempt_outcome(
    db: Session,
    provider: str,
    *,
    billed: bool | None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    values: dict[str, int] = {}
    if billed is True:
        values["billable_calls"] = 1
    elif billed is None:
        values["unknown_billing_calls"] = 1
    values["input_tokens"] = int(input_tokens or 0)
    values["output_tokens"] = int(output_tokens or 0)
    _increment(db, provider, **values)
    if provider != "_all":
        _increment(db, "_all", **values)
    db.commit()


def _increment(db: Session, provider: str, **increments: int) -> None:
    increments = {key: amount for key, amount in increments.items() if amount}
    if not increments:
        return
    table = AiUsageDaily.__table__
    now = datetime.now(timezone.utc)
    values = {
        "day": _today_utc(),
        "provider": provider,
        "updated_at": now,
        **increments,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgres_insert(table).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(table).values(**values)
    else:  # pragma: no cover
        raise RuntimeError(f"Unsupported usage-ledger dialect: {dialect}")
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.day, table.c.provider],
        set_={
            **{key: getattr(table.c, key) + amount for key, amount in increments.items()},
            "updated_at": now,
        },
    )
    db.execute(statement)
