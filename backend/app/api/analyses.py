"""AI analysis endpoints (Phase 5, P5.6): run a Claude verdict + read history.

`POST /{ticker}/analyses` builds the dossier (services/dossier.py) + recent
forum posts, DISTILS those posts into confidence-labelled claims (P5.9,
services/forum_distiller.py — never raw opinions), assembles the skill
prompt (services/prompts.py), and calls Claude forced into the verdict JSON
schema (services/claude_client.py). A global daily cap
(`settings.ai_daily_limit`, PLAN §9a "Cost guard") protects the API bill from
enthusiastic friends — enforced here, not in the client, since it is a
cross-request/global concern.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_user_email
from app.api.schemas import AnalysisOut
from app.config import get_settings
from app.db.base import get_db
from app.db.models import Analysis, Company, ForumPost, ForumTopic
from app.services import claude_client
from app.services import dossier as dossier_service
from app.services import forum_distiller
from app.services import prompts as prompts_service

router = APIRouter(prefix="/companies", tags=["analyses"])

# Cap on how many recent forum posts are ever handed to the prompt assembler;
# `services/prompts.py` applies a further ~30k-char budget on top of this.
_FORUM_POST_LIMIT = 40


def _get_company_or_404(db: Session, ticker: str) -> Company:
    """Same lookup as `app/api/companies.py`/`forum.py` — kept local rather
    than importing a private helper across router modules (existing repo
    convention: each router owns its own 404)."""
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


def _recent_forum_posts(db: Session, company_id: int, limit: int = _FORUM_POST_LIMIT) -> list[dict]:
    """Posts across every topic linked to this company, newest first — the
    same join shape as `app/api/forum.py::get_company_posts`."""
    rows = db.scalars(
        select(ForumPost)
        .join(ForumTopic, ForumPost.topic_id == ForumTopic.id)
        .where(ForumTopic.company_id == company_id)
        .order_by(ForumPost.posted_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "post_id": row.phpbb_post_id,
            "author": row.author,
            "posted_at": row.posted_at,
            "upvotes": row.upvotes,
            "content_text": row.content_text,
        }
        for row in rows
    ]


@router.post("/{ticker}/analyses", response_model=AnalysisOut)
def run_analysis(
    ticker: str,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
) -> Analysis:
    company = _get_company_or_404(db, ticker)
    settings = get_settings()

    limit = int(getattr(settings, "ai_daily_limit", 20) or 20)
    today_count = db.scalar(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.created_at >= _start_of_today_utc())
    )
    if int(today_count or 0) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Osiągnięto dzienny limit analiz AI ({limit}). Spróbuj ponownie jutro.",
        )

    dossier = dossier_service.build_dossier(db, company)
    forum_posts = _recent_forum_posts(db, company.id)
    # P5.9: distil raw posts into confidence-labelled claims BEFORE they ever
    # reach the verdict prompt — triggers zero new forum HTTP requests (it
    # runs over `forum_posts`, already fetched from the DB above), and is
    # itself cached per post, so a re-run over unchanged posts costs no
    # extra Claude calls either. No key configured ⇒ `forum_claims` comes
    # back empty (never raises) and the prompt still assembles cleanly.
    forum_claims = forum_distiller.distill_company_posts(forum_posts, settings=settings)
    prompt_bundle = prompts_service.build_analysis_prompt(
        dossier, forum_posts, forum_claims=forum_claims
    )

    try:
        result = claude_client.run_analysis(prompt_bundle, settings=settings, ticker=company.ticker)
    except claude_client.AnalysisUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analiza AI wymaga skonfigurowania ANTHROPIC_API_KEY.",
        )

    record = Analysis(
        company_id=company.id,
        model=result.model,
        prescore=dossier["prescore"],
        output=result.verdict,
        alignment_score=result.verdict.get("alignment_score"),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        created_by=user_email,
    )
    db.add(record)
    db.commit()
    return record


@router.get("/{ticker}/analyses", response_model=list[AnalysisOut])
def list_analyses(ticker: str, db: Session = Depends(get_db)) -> list[Analysis]:
    company = _get_company_or_404(db, ticker)
    return db.scalars(
        select(Analysis)
        .where(Analysis.company_id == company.id)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
    ).all()
