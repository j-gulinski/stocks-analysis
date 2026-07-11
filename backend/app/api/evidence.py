"""Read-only evidence ledger endpoints with point-in-time selection."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Company, DataConflict, DocumentVersion, Fact, SourceDocument
from app.services import evidence as evidence_service
from app.services.source_quality import source_quality_note

router = APIRouter(prefix="/companies", tags=["evidence"])


def _company_or_404(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown company '{ticker.upper()}'.",
        )
    return company


@router.get("/{ticker}/evidence/documents")
def list_documents(ticker: str, db: Session = Depends(get_db)) -> list[dict]:
    company = _company_or_404(db, ticker)
    documents = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.company_ticker == company.ticker)
        .order_by(SourceDocument.source_type, SourceDocument.scope_key)
    ).all()
    result: list[dict] = []
    for document in documents:
        version_stats = db.execute(
            select(
                func.count(DocumentVersion.id),
                func.min(DocumentVersion.fetched_at),
                func.max(DocumentVersion.fetched_at),
            ).where(DocumentVersion.source_document_id == document.id)
        ).one()
        latest_version = db.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.source_document_id == document.id)
            .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
            .limit(1)
        )
        result.append(
            {
                "id": document.id,
                "source_name": document.source_name,
                "source_type": document.source_type,
                "scope_key": document.scope_key,
                "canonical_url": document.canonical_url,
                "first_seen_at": document.first_seen_at,
                "last_fetched_at": document.last_fetched_at,
                "latest_content_hash": document.latest_content_hash,
                "parser_version": document.parser_version,
                "last_fetch_status": document.last_fetch_status,
                "version_count": int(version_stats[0] or 0),
                "first_version_at": version_stats[1],
                "latest_version_at": version_stats[2],
                "latest_parse_status": (
                    latest_version.parse_status if latest_version else "missing"
                ),
                "latest_parse_error": latest_version.parse_error if latest_version else None,
                "quality": source_quality_note(document.source_type),
            }
        )
    return result


@router.get("/{ticker}/evidence/facts")
def list_facts_as_of(
    ticker: str,
    as_of: datetime | None = Query(default=None),
    fact_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    company = _company_or_404(db, ticker)
    cutoff = as_of or datetime.now(timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    rows = evidence_service.facts_as_of(
        db, company.ticker, cutoff, fact_type=fact_type
    )
    return [
        {
            "id": fact.id,
            "fact_type": fact.fact_type,
            "fact_key": fact.fact_key,
            "numeric_value": float(fact.numeric_value) if fact.numeric_value is not None else None,
            "text_value": fact.text_value,
            "unit": fact.unit,
            "period": fact.period,
            "known_at": fact.known_at,
            "verification_state": fact.verification_state,
            "locator": fact.locator,
            "source": {
                "document_id": document.id,
                "version_id": version.id,
                "source_name": document.source_name,
                "source_type": document.source_type,
                "scope_key": document.scope_key,
                "url": version.effective_url,
                "content_hash": version.content_hash,
                "fetched_at": version.fetched_at,
                "parse_status": version.parse_status,
            },
        }
        for fact, version, document in rows
    ]


@router.get("/{ticker}/evidence/conflicts")
def list_conflicts(ticker: str, db: Session = Depends(get_db)) -> list[dict]:
    company = _company_or_404(db, ticker)
    conflicts = db.scalars(
        select(DataConflict)
        .where(DataConflict.company_ticker == company.ticker)
        .order_by(DataConflict.status, DataConflict.created_at.desc())
    ).all()
    return [
        {
            "id": conflict.id,
            "fact_key": conflict.fact_key,
            "period": conflict.period,
            "status": conflict.status,
            "left_fact_id": conflict.left_fact_id,
            "right_fact_id": conflict.right_fact_id,
            "left_value": (
                float(left.numeric_value) if left and left.numeric_value is not None else None
            ),
            "right_value": (
                float(right.numeric_value) if right and right.numeric_value is not None else None
            ),
            "resolution_rule": conflict.resolution_rule,
            "created_at": conflict.created_at,
        }
        for conflict in conflicts
        for left, right in [
            (db.get(Fact, conflict.left_fact_id), db.get(Fact, conflict.right_fact_id))
        ]
    ]
