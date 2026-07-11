"""Market candidate discovery; source ranking stays distinct from strategy fit."""
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    CompanyOut,
    DiscoveryCandidateOut,
    DiscoveryEvaluationJobOut,
    DiscoveryOut,
    DiscoveryScheduleOut,
    DiscoveryTriagePromotionOut,
    DiscoveryTriageReviewCreateIn,
    DiscoveryTriageReviewOut,
)
from app.api.deps import get_user_email
from app.db.base import get_db
from app.db.models import AgentRun, AnalysisRun, Company, DiscoveryTriageReview, DocumentVersion, ResearchCase, ResearchCaseStepHistory, SourceDocument
from app.scrapers.biznesradar import ParseError, parse_market_rating
from app.services.discovery import discover_candidates
from app.services.forecast_ranking import build_forecast_growth_ranking
from app.services import universe_policy

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/forecast-growth")
def forecast_growth_ranking(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    return build_forecast_growth_ranking(db, limit=limit)


@router.post("/universe-policy/refresh")
def refresh_universe_policy(db: Session = Depends(get_db)) -> dict:
    """Explicitly refresh the two official GPW Benchmark exclusion portfolios."""
    return {"memberships": [universe_policy.refresh_membership(db, name) for name in ("WIG20", "mWIG40")]}


@router.get("/universe-policy")
def get_universe_policy(db: Session = Depends(get_db)) -> dict:
    """Explain default inclusion/exclusion from stored dated membership evidence."""
    result = discover_candidates(db, force=False)
    return universe_policy.policy_for_candidates(db, result.candidates)

_RATING_RANK = {
    "AAA": 16, "AA+": 15, "AA": 14, "AA-": 13,
    "A+": 12, "A": 11, "A-": 10,
    "BBB+": 9, "BBB": 8, "BBB-": 7,
    "BB+": 6, "BB": 5, "BB-": 4,
    "B+": 3, "B": 2, "B-": 1,
}

_RECALL_MIN_RATING = 5.0
_RECALL_POLICY = "recall-v1"
_EVALUATION_CANDIDATE_LIMIT = 300
_EVALUATION_BUDGET = 12
_ANALYSIS_TOP_LIMIT = 15
_ANALYSIS_STALE_DAYS = 7


def _sort_key(candidate) -> tuple:
    return (
        -_RATING_RANK.get(candidate.rating or "", 0),
        -(candidate.piotroski_f_score if candidate.piotroski_f_score is not None else -1),
        -(candidate.rating_value if candidate.rating_value is not None else -9999),
        candidate.ticker,
    )


def _select_candidates(candidates, *, min_rating: float, min_f_score: int | None):
    selected = [
        candidate
        for candidate in candidates
        if candidate.rating_value is not None
        and candidate.rating_value >= min_rating
        and (
            min_f_score is None
            or (
                candidate.piotroski_f_score is not None
                and candidate.piotroski_f_score >= min_f_score
            )
        )
    ]
    selected.sort(key=_sort_key)
    return selected


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _rank_basis(candidate, rank: int, total: int) -> list[str]:
    f_score = (
        f"Piotroski F-Score {candidate.piotroski_f_score}/9 jest drugim kryterium rozstrzygającym."
        if candidate.piotroski_f_score is not None
        else "Brak Piotroski F-Score, więc ta spółka nie zyskuje punktu w tym kryterium."
    )
    return [
        f"Pozycja źródłowa {rank}/{total} w wybranym szerokim sicie.",
        "Kolejność: poziom ratingu BR, Piotroski F-Score, wartość ratingu, ticker.",
        f"Rating BR {candidate.rating or 'brak'} ({candidate.rating_value if candidate.rating_value is not None else 'b/d'}).",
        f_score,
    ]


def _schedule_stale_analyses(db: Session, result) -> DiscoveryScheduleOut:
    """Queue one bounded initial-research request for each new top-15 row."""
    top = _select_candidates(
        result.candidates,
        min_rating=_RECALL_MIN_RATING,
        min_f_score=None,
    )[:_ANALYSIS_TOP_LIMIT]
    cutoff = datetime.now(timezone.utc) - timedelta(days=_ANALYSIS_STALE_DAYS)
    queued_tickers: list[str] = []
    skipped_recent = 0
    skipped_pending = 0
    skipped_not_stored = 0

    for rank, candidate in enumerate(top, start=1):
        idempotency_key = f"discovery-initial-research:{result.source_version_id}:{candidate.ticker}"
        existing = db.scalar(
            select(AgentRun).where(AgentRun.idempotency_key == idempotency_key)
        )
        if existing is not None:
            skipped_pending += 1
            continue
        db.add(
            AgentRun(
                workflow="stock-initial-research",
                trigger="discovery-new-top-15",
                status="queued",
                model_role="worker_standard",
                model="gpt-5.6-terra",
                orchestrator_model="gpt-5.6-terra",
                idempotency_key=idempotency_key,
                inputs={
                    "ticker": candidate.ticker,
                    "source": "biznesradar-market-rating",
                    "source_document_version_id": result.source_version_id,
                    "source_as_of": result.fetched_at.isoformat(),
                    "candidate_rank": rank,
                    "source_signals": {
                        "br_rating": candidate.rating,
                        "br_rating_value": candidate.rating_value,
                        "piotroski_f_score": candidate.piotroski_f_score,
                        "report_period": candidate.report_period,
                    },
                    "task": {
                        "skill": "stock-quick-analysis",
                        "objective": (
                            "Refresh this new top-15 discovery candidate, then "
                            "prepare its first verifier-gated research read."
                        ),
                        "required_verification": "verifier_strict",
                        "watchlist_policy": "do not add automatically",
                    },
                },
                outputs={},
            )
        )
        queued_tickers.append(candidate.ticker)

    if queued_tickers:
        db.commit()
    return DiscoveryScheduleOut(
        considered=len(top),
        queued=len(queued_tickers),
        skipped_recent=skipped_recent,
        skipped_pending=skipped_pending,
        skipped_not_stored=skipped_not_stored,
        tickers=queued_tickers,
        stale_after_days=_ANALYSIS_STALE_DAYS,
    )


def _ensure_evaluation_job(db: Session, result) -> DiscoveryEvaluationJobOut | None:
    candidates = _select_candidates(
        result.candidates,
        min_rating=_RECALL_MIN_RATING,
        min_f_score=None,
    )[:_EVALUATION_CANDIDATE_LIMIT]
    if not candidates:
        return None

    job_key = (
        f"biznesradar-market-rating:{result.source_version_id}:{_RECALL_POLICY}"
    )
    existing = db.scalar(
        select(AgentRun).where(AgentRun.idempotency_key == job_key)
    )
    if existing is not None:
        return DiscoveryEvaluationJobOut(
            id=existing.id,
            status=existing.status,
            candidate_count=int((existing.inputs or {}).get("candidate_count") or 0),
            evaluation_budget=int((existing.inputs or {}).get("evaluation_budget") or 0),
            reused=True,
        )

    evaluation_budget = min(_EVALUATION_BUDGET, len(candidates))
    agent = AgentRun(
        workflow="stock-candidate-scout",
        trigger="discovery-refresh",
        status="queued",
        model_role="worker_standard",
        model="gpt-5.6-terra",
        orchestrator_model="gpt-5.6-terra",
        idempotency_key=job_key,
        inputs={
            "job_key": job_key,
            "policy": _RECALL_POLICY,
            "source": "biznesradar-market-rating",
            "source_document_version_id": result.source_version_id,
            "source_url": result.source_url,
            "source_as_of": result.fetched_at.isoformat(),
            "candidate_count": len(candidates),
            "evaluation_budget": evaluation_budget,
            "batch_size": 4,
            "candidates": [
                {
                    "ticker": candidate.ticker,
                    "name": candidate.name,
                    "report_period": candidate.report_period,
                    "br_rating": candidate.rating,
                    "br_rating_value": candidate.rating_value,
                    "piotroski_f_score": candidate.piotroski_f_score,
                }
                for candidate in candidates
            ],
            "task": {
                "skill": "stock-candidate-scout",
                "objective": (
                    "Run a source-only prescreen over the complete recall-first "
                    "shortlist, rate the top budgeted candidates, and identify "
                    "which dossiers merit a later bounded refresh."
                ),
                "required_verification": "verifier_strict for every promoted candidate",
                "verifier_model_role": "verifier_strict",
                "refresh_policy": "do not auto-refresh or create hundreds of companies",
                "watchlist_policy": "never add a candidate without user approval",
            },
        },
        outputs={},
    )
    db.add(agent)
    try:
        db.commit()
    except IntegrityError:
        # Two simultaneous Discover reads may both observe the same new source
        # version. The unique key makes one the winner without duplicating work.
        db.rollback()
        winner = db.scalar(
            select(AgentRun).where(AgentRun.idempotency_key == job_key)
        )
        if winner is None:  # pragma: no cover - defensive DB failure path
            raise
        return DiscoveryEvaluationJobOut(
            id=winner.id,
            status=winner.status,
            candidate_count=int((winner.inputs or {}).get("candidate_count") or 0),
            evaluation_budget=int((winner.inputs or {}).get("evaluation_budget") or 0),
            reused=True,
        )
    return DiscoveryEvaluationJobOut(
        id=agent.id,
        status=agent.status,
        candidate_count=len(candidates),
        evaluation_budget=evaluation_budget,
        reused=False,
    )


@router.get("", response_model=DiscoveryOut)
def list_candidates(
    min_rating: float = Query(default=_RECALL_MIN_RATING, ge=-1000, le=1000),
    min_f_score: int | None = Query(default=None, ge=0, le=9),
    limit: int = Query(default=300, ge=1, le=300),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> DiscoveryOut:
    try:
        result = discover_candidates(db, force=force)
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "BiznesRadar discovery wymaga uwagi: zapisany widok rankingu "
                f"nie został rozpoznany ({exc}). Nie uruchamiaj kolejnych odświeżeń; "
                "sprawdź stan źródła lub fixture parsera."
            ),
        ) from exc
    selected = _select_candidates(
        result.candidates,
        min_rating=min_rating,
        min_f_score=min_f_score,
    )
    candidates = []
    selected_page = selected[:limit]
    for rank, candidate in enumerate(selected_page, start=1):
        reasons = [f"Rating BR {candidate.rating} ({candidate.rating_value:g})"]
        if candidate.piotroski_f_score is not None:
            reasons.append(f"Piotroski F-Score {candidate.piotroski_f_score}/9")
        candidates.append(
            DiscoveryCandidateOut(
                ticker=candidate.ticker,
                name=candidate.name,
                report_period=candidate.report_period,
                br_rating=candidate.rating,
                br_rating_value=candidate.rating_value,
                piotroski_f_score=candidate.piotroski_f_score,
                rank=rank,
                rank_basis=_rank_basis(candidate, rank, len(selected)),
                reasons=reasons,
                caveat=(
                    "Brak Piotroski F-Score — zachowano w szerokim sicie; "
                    "dossier i jakość wyniku wymagają weryfikacji."
                    if candidate.piotroski_f_score is None
                    else "Pełne dopasowanie do strategii jeszcze niezweryfikowane."
                ),
            )
        )
    evaluation_job = _ensure_evaluation_job(db, result)
    scheduled_analysis = _schedule_stale_analyses(db, result) if result.source_version_created else None
    return DiscoveryOut(
        source="BiznesRadar",
        source_url=result.source_url,
        as_of=result.fetched_at,
        universe_count=len(result.candidates),
        result_count=len(candidates),
        source_note=result.source_note,
        source_version_id=result.source_version_id,
        candidates=candidates,
        evaluation_job=evaluation_job,
        scheduled_analysis=scheduled_analysis,
    )


def _triage_out(row: DiscoveryTriageReview) -> DiscoveryTriageReviewOut:
    return DiscoveryTriageReviewOut.model_validate(row)


@router.get("/triage-reviews", response_model=list[DiscoveryTriageReviewOut])
def list_triage_reviews(
    source_version_id: int = Query(ge=1),
    db: Session = Depends(get_db),
) -> list[DiscoveryTriageReviewOut]:
    rows = db.scalars(
        select(DiscoveryTriageReview)
        .where(DiscoveryTriageReview.source_document_version_id == source_version_id)
        .order_by(DiscoveryTriageReview.created_at.desc(), DiscoveryTriageReview.id.desc())
    ).all()
    return [_triage_out(row) for row in rows]


@router.post("/triage-reviews", response_model=DiscoveryTriageReviewOut, status_code=status.HTTP_201_CREATED)
def create_triage_review(
    payload: DiscoveryTriageReviewCreateIn,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
) -> DiscoveryTriageReviewOut:
    version = db.scalar(
        select(DocumentVersion)
        .join(SourceDocument, DocumentVersion.source_document_id == SourceDocument.id)
        .where(
            DocumentVersion.id == payload.source_document_version_id,
            SourceDocument.company_ticker == "__GPW__",
            SourceDocument.source_type == "market_rating",
            DocumentVersion.parse_status == "parsed",
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Unknown parsed discovery source version.")
    tickers = {candidate.ticker for candidate in parse_market_rating(version.raw_content)}
    ticker = payload.ticker.strip().upper()
    if ticker not in tickers:
        raise HTTPException(status_code=422, detail="Ticker is not present in this immutable discovery version.")
    row = DiscoveryTriageReview(
        source_document_version_id=version.id, ticker=ticker,
        review_price_pln=payload.review_price_pln, note=payload.note.strip(),
        outcome=payload.outcome, next_review_date=payload.next_review_date,
        evidence_reason=payload.evidence_reason.strip(), created_by=user_email,
    )
    db.add(row); db.commit(); db.refresh(row)
    return _triage_out(row)


@router.post(
    "/triage-reviews/{review_id}/promote",
    response_model=DiscoveryTriagePromotionOut,
    status_code=status.HTTP_201_CREATED,
)
def promote_triage_review(
    review_id: int,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
) -> DiscoveryTriagePromotionOut:
    """Explicitly turn one human triage decision into a durable research case.

    This action creates no watchlist item, trade or recurring worker.  It only
    preserves the human triage context, schedules a dated quarterly review in
    the case record and queues the initial research for a user-invoked Codex
    worker.
    """
    review = db.get(DiscoveryTriageReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Discovery triage review not found.")
    if review.outcome != "promote_to_case":
        raise HTTPException(
            status_code=422,
            detail="Only a triage review marked promote_to_case can create a research case.",
        )
    version = db.get(DocumentVersion, review.source_document_version_id)
    if version is None or version.parse_status != "parsed":  # defensive provenance gate
        raise HTTPException(status_code=409, detail="The triage source version is no longer usable.")
    candidate = next(
        (row for row in parse_market_rating(version.raw_content) if row.ticker == review.ticker),
        None,
    )
    if candidate is None:
        raise HTTPException(status_code=409, detail="Ticker is not present in the frozen triage source.")

    company = db.scalar(select(Company).where(Company.ticker == review.ticker))
    created_company = company is None
    if company is None:
        company = Company(
            ticker=review.ticker,
            name=candidate.name,
            br_slug=candidate.br_slug,
            market="GPW",
        )
        db.add(company)
        db.flush()

    research_case = db.scalar(
        select(ResearchCase).where(
            ResearchCase.company_id == company.id,
            ResearchCase.purpose == "investment-research",
        )
    )
    created_case = research_case is None
    if research_case is None:
        research_case = ResearchCase(
            company_id=company.id,
            purpose="investment-research",
            state="ingesting",
            current_step="ingest",
            as_of=review.created_at,
            promotion_triage_review_id=review.id,
            promotion_review_price_pln=review.review_price_pln,
            promotion_note=review.note,
            promotion_evidence_reason=review.evidence_reason,
            quarterly_review_due_on=review.next_review_date,
            material_event_review_policy="manual-after-stored-event",
        )
        db.add(research_case)
        db.flush()
        db.add(
            ResearchCaseStepHistory(
                research_case_id=research_case.id,
                from_state=None,
                from_step=None,
                to_state="ingesting",
                to_step="ingest",
                reason=(
                    f"Promoted from triage #{review.id} at {review.review_price_pln} PLN: "
                    f"{review.note}"
                ),
                changed_by=user_email,
            )
        )
    elif research_case.promotion_triage_review_id != review.id:
        raise HTTPException(
            status_code=409,
            detail="An investment-research case already exists; its promotion provenance is not overwritten.",
        )

    run_key = f"triage-promotion-initial-research:{review.id}"
    agent = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == run_key))
    if agent is None:
        agent = AgentRun(
            workflow="stock-deep-analysis",
            trigger="triage-promotion",
            status="queued",
            company_id=company.id,
            model_role="worker_standard",
            model="gpt-5.6-terra",
            orchestrator_model="gpt-5.6-terra",
            idempotency_key=run_key,
            inputs={
                "ticker": company.ticker,
                "research_case_id": research_case.id,
                "promotion": {
                    "triage_review_id": review.id,
                    "source_document_version_id": review.source_document_version_id,
                    "review_price_pln": float(review.review_price_pln),
                    "note": review.note,
                    "evidence_reason": review.evidence_reason,
                    "quarterly_review_due_on": review.next_review_date.isoformat(),
                    "material_event_review_policy": "manual-after-stored-event",
                },
                "task": {
                    "skill": "stock-deep-analysis",
                    "objective": "Build the first source-grounded research case from the promoted human triage.",
                    "required_verification": "verifier_strict",
                    "watchlist_policy": "do not add automatically",
                    "automation_policy": "user invokes the one-shot queue skill; do not start a recurring worker",
                },
            },
            outputs={},
        )
        db.add(agent)
        db.flush()
    quarterly_key = f"research-case-quarterly-review:{research_case.id}:{review.next_review_date.isoformat()}"
    quarterly_agent = db.scalar(select(AgentRun).where(AgentRun.idempotency_key == quarterly_key))
    if quarterly_agent is None:
        quarterly_agent = AgentRun(
            workflow="stock-thesis-review",
            trigger="triage-promotion-quarterly-review",
            status="queued",
            company_id=company.id,
            model_role="analyst_deep",
            model="gpt-5.6-sol",
            orchestrator_model="gpt-5.6-sol",
            available_at=datetime.combine(review.next_review_date, time.min, tzinfo=timezone.utc),
            idempotency_key=quarterly_key,
            inputs={
                "ticker": company.ticker,
                "research_case_id": research_case.id,
                "review_kind": "quarterly",
                "promotion_triage_review_id": review.id,
                "task": {
                    "skill": "stock-thesis-review",
                    "objective": "Revisit the thesis against the promoted-case baseline and newly stored evidence.",
                    "required_verification": "verifier_strict",
                    "automation_policy": "due work waits for a user-invoked one-shot queue worker",
                },
            },
            outputs={},
        )
        db.add(quarterly_agent)
        db.flush()
    db.commit()
    db.refresh(company)
    db.refresh(research_case)
    return DiscoveryTriagePromotionOut(
        company=CompanyOut.model_validate(company),
        research_case=research_case,
        initial_research_run_id=agent.id,
        quarterly_review_run_id=quarterly_agent.id,
        created_company=created_company,
        created_case=created_case,
    )
