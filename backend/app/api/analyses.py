"""Explicit, audited full-company analysis runs and successful-run history.

The endpoint delegates provider work to ``analysis.orchestrator``.  Legacy
formatting/ranking helpers remain here because older clients and tests import
them, but they no longer bypass the durable run, quota, and model-call ledger.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis import orchestrator
from app.api.deps import get_user_email
from app.api.schemas import AnalysisOut
from app.config import get_settings
from app.db.base import get_db
from app.db.models import Analysis, Company
from app.services import claude_client

router = APIRouter(prefix="/companies", tags=["analyses"])
_MAX_FORUM_CLAIMS_FOR_AI = 12

def _fact_rank(item: dict) -> tuple[int, int, int]:
    confidence_rank = {"confirmed": 4, "high": 3, "medium": 2, "low": 1}
    type_rank = {
        "expectation": 5,
        "risk": 4,
        "catalyst": 4,
        "dividend": 3,
        "valuation": 3,
        "fact_claim": 1,
    }
    source_ids = item.get("source_post_ids") or []
    latest_source = max((int(x) for x in source_ids if isinstance(x, int)), default=0)
    return (
        confidence_rank.get(str(item.get("confidence") or "").lower(), 0),
        type_rank.get(str(item.get("type") or ""), 0),
        latest_source,
    )


def _get_company_or_404(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown company '{ticker.upper()}'.",
        )
    return company


def _start_of_today_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def count_analyses_today(db: Session) -> int:
    """Analysis rows created today (UTC) — the exact query the daily cap
    below enforces. Deliberately NOT underscore-prefixed and imported by
    `app/api/diagnostics.py`'s `/ai-status` rather than re-derived there:
    unlike `_get_company_or_404` above (duplicated per router on purpose —
    a trivial lookup where drift is harmless), this number is the actual
    cost-guard arithmetic, so a diagnostics endpoint computing it a slightly
    different way would risk silently lying about how much cap is left.
    """
    today_count = db.scalar(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.created_at >= _start_of_today_utc())
    )
    return int(today_count or 0)


def _unavailable_to_http(
    exc: claude_client.AnalysisUnavailable, model: str
) -> HTTPException:
    """Map `AnalysisUnavailable.reason` to its HTTP status + Polish message.

    Factored out of `run_analysis` so it is unit-testable directly (construct
    an `AnalysisUnavailable`, call this, assert on the returned
    `HTTPException`) without spinning up a TestClient/DB.
    """
    if exc.reason == "transport":
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Analiza AI nie powiodła się: błąd wywołania API Claude "
                f"(model {model}). Szczegóły: {exc.detail}"
            ),
        )
    if exc.reason == "parse":
        suffix = f" Szczegóły: {exc.detail}" if exc.detail else ""
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Analiza AI nie powiodła się: niepoprawna odpowiedź modelu — "
                f"spróbuj ponownie.{suffix}"
            ),
        )
    # "no_key" — and, defensively, any future/unrecognized reason: the
    # original catch-all message, the one case where the fix genuinely IS
    # "set ANTHROPIC_API_KEY".
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Analiza AI wymaga skonfigurowania ANTHROPIC_API_KEY.",
    )


def _forum_claims_from_intelligence(dossier: dict) -> list[dict]:
    """Forum claims for the verdict prompt, preferring the AI-distilled read.

    `intelligence.expectations.claims` (services/forum_expectations.py, an
    actual Claude classification of forum post arguments) wins whenever it is
    non-empty — it already comes deduplicated and upvote-ranked out of
    `forum_distiller.distill_company_posts`, so we just cap it at the same
    limit. Falls back to the keyword-heuristic `distilled_facts` (pre-P5.9b
    behaviour) only when no AI expectations exist yet (no API key configured,
    or `refresh_expectations` hasn't run for this company)."""
    intelligence = (dossier.get("forum") or {}).get("intelligence") or {}

    expectations = intelligence.get("expectations") or {}
    ai_claims = [
        item
        for item in (expectations.get("claims") or [])
        if isinstance(item, dict) and item.get("claim")
    ]
    if ai_claims:
        return [
            {
                "claim": item["claim"],
                "confidence": item.get("confidence") or "medium",
                "type": item.get("type") or "opinion",
                "source_post_ids": item.get("source_post_ids") or [],
            }
            for item in ai_claims[:_MAX_FORUM_CLAIMS_FOR_AI]
        ]

    facts = [
        item
        for item in (intelligence.get("distilled_facts") or [])
        if isinstance(item, dict) and item.get("fact")
    ]
    claims: list[dict] = []
    for item in sorted(facts, key=_fact_rank, reverse=True)[:_MAX_FORUM_CLAIMS_FOR_AI]:
        claims.append(
            {
                "claim": item["fact"],
                "confidence": item.get("confidence") or "medium",
                "type": item.get("topic") or "fact-claim",
                "source_post_ids": item.get("source_post_ids") or [],
            }
        )
    return claims


def _snapshot_hash(snapshot: dict) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_safe(obj):
    """Round-trip through JSON so DB JSONB never sees date/Decimal objects."""
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))
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
