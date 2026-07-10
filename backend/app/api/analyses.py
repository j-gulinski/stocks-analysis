"""Explicit full-company analysis runs and successful-run history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis import orchestrator
from app.api.deps import get_user_email
from app.api.schemas import AnalysisOut
from app.config import get_settings
from app.db.base import get_db
from app.db.models import Analysis, Company

router = APIRouter(prefix="/companies", tags=["analyses"])


def _get_company_or_404(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown company '{ticker.upper()}'.",
        )
    return company


@router.post("/{ticker}/analyses", response_model=AnalysisOut)
def run_analysis(
    ticker: str,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Analysis:
    company = _get_company_or_404(db, ticker)
    try:
        return orchestrator.run_analysis(
            db,
            company,
            get_settings(),
            user_email=user_email,
            idempotency_key=idempotency_key,
        )
    except orchestrator.AnalysisRunError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail=exc.public_detail,
        ) from exc


@router.get("/{ticker}/analyses", response_model=list[AnalysisOut])
def list_analyses(ticker: str, db: Session = Depends(get_db)) -> list[Analysis]:
    company = _get_company_or_404(db, ticker)
    return db.scalars(
        select(Analysis)
        .where(
            Analysis.company_id == company.id,
            Analysis.status == "succeeded",
        )
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
    ).all()
