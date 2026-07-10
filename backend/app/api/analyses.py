"""AI analysis endpoints (Phase 5, P5.6): run a Claude verdict + read history.

`POST /{ticker}/analyses` builds the dossier (services/dossier.py), reads the
structured `forum_intelligence` block produced during sync, assembles the skill
prompt (services/prompts.py), and calls Claude forced into the verdict JSON
schema (services/claude_client.py). A global daily cap
(`settings.ai_daily_limit`, PLAN §9a "Cost guard") protects the API bill from
enthusiastic friends — enforced here, not in the client, since it is a
cross-request/global concern.

`claude_client.AnalysisUnavailable.reason` ("no_key" / "transport" / "parse")
is mapped to its HTTP status + Polish message by `_unavailable_to_http`
below — a catch-all 503 used to blame a missing key even when the key was
present and the transport call or response parsing failed instead.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_user_email
from app.api.schemas import AnalysisOut
from app.config import get_settings
from app.db.base import get_db
from app.db.models import Analysis, Company
from app.services import claude_client
from app.services import dossier as dossier_service
from app.services import prompts as prompts_service

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
) -> Analysis:
    company = _get_company_or_404(db, ticker)
    settings = get_settings()

    limit = int(getattr(settings, "ai_daily_limit", 20) or 20)
    today_count = count_analyses_today(db)
    if today_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Osiągnięto dzienny limit analiz AI ({limit}). Spróbuj ponownie jutro.",
        )

    dossier = dossier_service.build_dossier(
        db, company, use_ai_refiners=bool(getattr(settings, "ai_refiners_enabled", True))
    )
    forum_claims = _forum_claims_from_intelligence(dossier)
    prompt_bundle = prompts_service.build_analysis_prompt(
        dossier, forum_posts=[], forum_claims=forum_claims
    )

    try:
        result = claude_client.run_analysis(prompt_bundle, settings=settings, ticker=company.ticker)
    except claude_client.AnalysisUnavailable as exc:
        raise _unavailable_to_http(exc, settings.anthropic_model)

    record = Analysis(
        company_id=company.id,
        model=result.model,
        prescore=dossier["prescore"],
        input_snapshot=_json_safe(prompt_bundle.get("snapshot") or {}),
        input_hash=_snapshot_hash(prompt_bundle.get("snapshot") or {}),
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
