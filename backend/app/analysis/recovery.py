"""Reconcile analysis/model rows left running by an interrupted process."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import Analysis, ModelCall
from app.analysis import usage

STALE_AFTER = timedelta(minutes=15)


def reconcile_stale_runs(
    db: Session,
    *,
    now: datetime | None = None,
    stale_after: timedelta = STALE_AFTER,
) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - stale_after
    runs = db.scalars(
        select(Analysis).where(
            Analysis.status == "running",
            or_(
                Analysis.heartbeat_at < cutoff,
                and_(
                    Analysis.heartbeat_at.is_(None),
                    Analysis.created_at < cutoff,
                ),
            ),
        )
    ).all()
    calls = db.scalars(
        select(ModelCall).where(
            ModelCall.status == "running",
            ModelCall.created_at < cutoff,
        )
    ).all()

    reconciled_calls = 0
    for call in calls:
        claimed = db.execute(
            update(ModelCall)
            .where(
                ModelCall.id == call.id,
                ModelCall.status == "running",
                ModelCall.created_at < cutoff,
            )
            .values(
                status="failed",
                error_code="stale_interrupted",
                error="Worker heartbeat expired before the model call completed.",
                completed_at=now,
                billed=None,
            )
        )
        if claimed.rowcount == 1:
            db.commit()
            usage.record_attempt_outcome(db, call.provider, billed=None)
            reconciled_calls += 1

    reconciled_runs = 0
    for run in runs:
        claimed = db.execute(
            update(Analysis)
            .where(
                Analysis.id == run.id,
                Analysis.status == "running",
                or_(
                    Analysis.heartbeat_at < cutoff,
                    and_(
                        Analysis.heartbeat_at.is_(None),
                        Analysis.created_at < cutoff,
                    ),
                ),
            )
            .values(
                status="failed",
                error="Worker heartbeat expired before the analysis completed.",
                validation={
                    **(run.validation or {}),
                    "status": "failed",
                    "error_code": "stale_interrupted",
                },
                completed_at=now,
                heartbeat_at=now,
            )
        )
        if claimed.rowcount == 1:
            db.commit()
            reconciled_runs += 1
    return {"analysis_runs": reconciled_runs, "model_calls": reconciled_calls}
