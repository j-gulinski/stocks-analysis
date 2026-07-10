"""Deterministic company monitor snapshots and change cards."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import MonitorChangeOut, MonitorCheckOut
from app.db.base import get_db
from app.db.models import Company, EventReport, MonitorChange, MonitorSnapshot
from app.services import dossier as dossier_service
from app.services import monitor as monitor_service

router = APIRouter(prefix="/companies", tags=["monitor"])


def _company_or_404(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown company '{ticker.upper()}'.",
        )
    return company


def _change_out(row: MonitorChange) -> MonitorChangeOut:
    return MonitorChangeOut(
        id=row.id,
        from_snapshot_id=row.from_snapshot_id,
        to_snapshot_id=row.to_snapshot_id,
        changes=row.changes or [],
        created_at=row.created_at,
    )


@router.get("/{ticker}/monitor/changes", response_model=list[MonitorChangeOut])
def list_monitor_changes(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[MonitorChangeOut]:
    company = _company_or_404(db, ticker)
    rows = db.scalars(
        select(MonitorChange)
        .where(MonitorChange.company_id == company.id)
        .order_by(MonitorChange.created_at.desc(), MonitorChange.id.desc())
        .limit(limit)
    ).all()
    return [_change_out(row) for row in rows]


@router.post("/{ticker}/monitor/check", response_model=MonitorCheckOut)
def check_monitor(ticker: str, db: Session = Depends(get_db)) -> MonitorCheckOut:
    """Capture current stored state and compare it with the previous baseline."""
    company = _company_or_404(db, ticker)
    dossier = dossier_service.build_dossier(db, company, use_ai_refiners=False)
    reports = db.scalars(
        select(EventReport).where(EventReport.company_id == company.id)
    ).all()
    event_dicts = [
        {
            "external_id": row.external_id,
            "title": row.title,
            "published_at": (
                row.published_at.isoformat() if row.published_at is not None else None
            ),
        }
        for row in reports
    ]
    current = monitor_service.build_snapshot(dossier, event_dicts)
    current_hash = monitor_service.snapshot_hash(current)
    previous = db.scalar(
        select(MonitorSnapshot)
        .where(MonitorSnapshot.company_id == company.id)
        .order_by(MonitorSnapshot.captured_at.desc(), MonitorSnapshot.id.desc())
        .limit(1)
    )
    captured_at = datetime.now(timezone.utc)
    snapshot = MonitorSnapshot(
        company_id=company.id,
        captured_at=captured_at,
        snapshot_hash=current_hash,
        snapshot=current,
        source="session",
    )
    db.add(snapshot)
    db.flush()

    change = None
    if previous is not None and previous.snapshot_hash != current_hash:
        changes = monitor_service.diff_snapshots(previous.snapshot, current)
        if changes:
            change = MonitorChange(
                company_id=company.id,
                from_snapshot_id=previous.id,
                to_snapshot_id=snapshot.id,
                changes=changes,
            )
            db.add(change)
            db.flush()
    db.commit()
    if change is not None:
        db.refresh(change)
    return MonitorCheckOut(
        baseline_exists=previous is not None,
        changed=change is not None,
        snapshot_id=snapshot.id,
        snapshot_hash=current_hash,
        change=_change_out(change) if change is not None else None,
    )
