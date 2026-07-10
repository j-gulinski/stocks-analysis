"""Append-only investor decision journal endpoints."""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_user_email
from app.api.schemas import DecisionJournalEntryCreateIn, DecisionJournalEntryOut
from app.db.base import get_db
from app.db.models import Company, DecisionJournalEntry

router = APIRouter(prefix="/companies", tags=["decision-journal"])


def _company_or_404(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown company '{ticker.upper()}'.",
        )
    return company


def _snapshot_hash(snapshot: dict) -> str | None:
    if not snapshot:
        return None
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _to_out(entry: DecisionJournalEntry, ticker: str) -> DecisionJournalEntryOut:
    return DecisionJournalEntryOut(
        id=entry.id,
        ticker=ticker,
        decision=entry.decision,
        confidence=entry.confidence,
        thesis=entry.thesis,
        invalidation=entry.invalidation,
        next_check=entry.next_check,
        review_date=entry.review_date,
        thesis_snapshot=entry.thesis_snapshot or {},
        thesis_hash=entry.thesis_hash,
        created_by=entry.created_by,
        created_at=entry.created_at,
    )


@router.get(
    "/{ticker}/decision-journal",
    response_model=list[DecisionJournalEntryOut],
)
def list_decision_journal(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[DecisionJournalEntryOut]:
    company = _company_or_404(db, ticker)
    entries = db.scalars(
        select(DecisionJournalEntry)
        .where(DecisionJournalEntry.company_id == company.id)
        .order_by(
            DecisionJournalEntry.created_at.desc(),
            DecisionJournalEntry.id.desc(),
        )
        .limit(limit)
    ).all()
    return [_to_out(entry, company.ticker) for entry in entries]


@router.post(
    "/{ticker}/decision-journal",
    response_model=DecisionJournalEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_decision_journal_entry(
    ticker: str,
    payload: DecisionJournalEntryCreateIn,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
) -> DecisionJournalEntryOut:
    company = _company_or_404(db, ticker)
    snapshot = dict(payload.thesis_snapshot)
    entry = DecisionJournalEntry(
        company_id=company.id,
        decision=payload.decision.strip(),
        confidence=payload.confidence,
        thesis=payload.thesis.strip(),
        invalidation=payload.invalidation.strip(),
        next_check=payload.next_check.strip(),
        review_date=payload.review_date,
        thesis_snapshot=snapshot,
        thesis_hash=_snapshot_hash(snapshot),
        created_by=user_email,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _to_out(entry, company.ticker)
