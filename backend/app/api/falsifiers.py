"""Explicit, user-managed thesis falsifier state."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.api.schemas import FalsifierCreateIn, FalsifierOut, FalsifierUpdateIn
from app.db.base import get_db
from app.db.models import Company, ThesisFalsifier

router = APIRouter(prefix="/companies", tags=["falsifiers"])

ALLOWED_STATUSES = {"holding", "warning", "fired"}


def _company_or_404(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown company '{ticker.upper()}'.",
        )
    return company


def _validate_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Falsifier status must be holding, warning or fired.",
        )
    return normalized


def _out(row: ThesisFalsifier, ticker: str) -> FalsifierOut:
    return FalsifierOut(
        id=row.id,
        ticker=ticker,
        key=row.key,
        statement=row.statement,
        status=row.status,
        reason=row.reason,
        review_date=row.review_date,
        thesis_hash=row.thesis_hash,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/{ticker}/falsifiers", response_model=list[FalsifierOut])
def list_falsifiers(ticker: str, db: Session = Depends(get_db)) -> list[FalsifierOut]:
    company = _company_or_404(db, ticker)
    rows = db.scalars(
        select(ThesisFalsifier)
        .where(ThesisFalsifier.company_id == company.id)
        .order_by(
            case(
                (ThesisFalsifier.status == "fired", 0),
                (ThesisFalsifier.status == "warning", 1),
                else_=2,
            ),
            ThesisFalsifier.id.asc(),
        )
    ).all()
    return [_out(row, company.ticker) for row in rows]


@router.post(
    "/{ticker}/falsifiers",
    response_model=FalsifierOut,
    status_code=status.HTTP_201_CREATED,
)
def create_falsifier(
    ticker: str,
    payload: FalsifierCreateIn,
    db: Session = Depends(get_db),
) -> FalsifierOut:
    company = _company_or_404(db, ticker)
    state = _validate_status(payload.status)
    existing = db.scalar(
        select(ThesisFalsifier).where(
            ThesisFalsifier.company_id == company.id,
            ThesisFalsifier.key == payload.key.strip(),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Falsifier '{payload.key.strip()}' already exists.",
        )
    row = ThesisFalsifier(
        company_id=company.id,
        key=payload.key.strip(),
        statement=payload.statement.strip(),
        status=state,
        reason=payload.reason.strip(),
        review_date=payload.review_date,
        thesis_hash=payload.thesis_hash,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row, company.ticker)


@router.patch("/{ticker}/falsifiers/{falsifier_id}", response_model=FalsifierOut)
def update_falsifier(
    ticker: str,
    falsifier_id: int,
    payload: FalsifierUpdateIn,
    db: Session = Depends(get_db),
) -> FalsifierOut:
    company = _company_or_404(db, ticker)
    row = db.scalar(
        select(ThesisFalsifier).where(
            ThesisFalsifier.id == falsifier_id,
            ThesisFalsifier.company_id == company.id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Falsifier not found.")
    row.status = _validate_status(payload.status)
    row.reason = payload.reason.strip()
    row.review_date = payload.review_date
    db.commit()
    db.refresh(row)
    return _out(row, company.ticker)
