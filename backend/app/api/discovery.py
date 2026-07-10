"""Market candidate discovery; source ranking stays distinct from strategy fit."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import (
    DiscoveryCandidateOut,
    DiscoveryEvaluationJobOut,
    DiscoveryOut,
    DiscoveryScheduleOut,
)
from app.db.base import get_db
from app.db.models import AgentRun, AnalysisRun, Company
from app.services.discovery import discover_candidates

router = APIRouter(prefix="/discovery", tags=["discovery"])

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
    """Queue at most 15 stored-company quick analyses after a source refetch."""
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
        company = db.scalar(select(Company).where(Company.ticker == candidate.ticker))
        if company is None:
            skipped_not_stored += 1
            continue

        latest_analysis = db.scalar(
            select(AnalysisRun.created_at)
            .where(AnalysisRun.company_id == company.id)
            .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
            .limit(1)
        )
        latest_utc = _aware_utc(latest_analysis)
        if latest_utc is not None and latest_utc >= cutoff:
            skipped_recent += 1
            continue

        idempotency_key = f"discovery-quick-analysis:{result.source_version_id}:{candidate.ticker}"
        existing = db.scalar(
            select(AgentRun).where(AgentRun.idempotency_key == idempotency_key)
        )
        if existing is not None:
            skipped_pending += 1
            continue
        pending = db.scalar(
            select(AgentRun.id)
            .where(
                AgentRun.company_id == company.id,
                AgentRun.workflow == "stock-quick-analysis",
                AgentRun.status.in_(("queued", "claimed", "running")),
            )
            .limit(1)
        )
        if pending is not None:
            skipped_pending += 1
            continue

        db.add(
            AgentRun(
                workflow="stock-quick-analysis",
                trigger="discovery-refresh",
                status="queued",
                company_id=company.id,
                model_role="analyst_deep",
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
                            "Refresh the stale top-ranked discovery candidate's "
                            "dossier and produce a verifier-gated quick analysis."
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
        model="gpt-5.3-codex-spark",
        orchestrator_model="gpt-5.3-codex-spark",
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
    result = discover_candidates(db, force=force)
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
    scheduled_analysis = _schedule_stale_analyses(db, result) if force else None
    return DiscoveryOut(
        source="BiznesRadar",
        source_url=result.source_url,
        as_of=result.fetched_at,
        universe_count=len(result.candidates),
        result_count=len(candidates),
        source_note=result.source_note,
        candidates=candidates,
        evaluation_job=evaluation_job,
        scheduled_analysis=scheduled_analysis,
    )
