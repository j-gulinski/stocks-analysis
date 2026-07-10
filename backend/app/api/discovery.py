"""Market candidate discovery; source ranking stays distinct from strategy fit."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.schemas import DiscoveryCandidateOut, DiscoveryOut
from app.db.base import get_db
from app.services.discovery import discover_candidates

router = APIRouter(prefix="/discovery", tags=["discovery"])

_RATING_RANK = {
    "AAA": 16, "AA+": 15, "AA": 14, "AA-": 13,
    "A+": 12, "A": 11, "A-": 10,
    "BBB+": 9, "BBB": 8, "BBB-": 7,
    "BB+": 6, "BB": 5, "BB-": 4,
    "B+": 3, "B": 2, "B-": 1,
}


@router.get("", response_model=DiscoveryOut)
def list_candidates(
    min_rating: float = Query(default=7.0, ge=-1000, le=1000),
    min_f_score: int | None = Query(default=5, ge=0, le=9),
    limit: int = Query(default=40, ge=1, le=200),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> DiscoveryOut:
    result = discover_candidates(db, force=force)
    selected = [
        candidate
        for candidate in result.candidates
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
    selected.sort(
        key=lambda candidate: (
            -_RATING_RANK.get(candidate.rating or "", 0),
            -(candidate.piotroski_f_score or -1),
            -(candidate.rating_value or -9999),
            candidate.ticker,
        )
    )
    candidates = []
    for candidate in selected[:limit]:
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
                reasons=reasons,
                caveat="Pełne dopasowanie do strategii jeszcze niezweryfikowane.",
            )
        )
    return DiscoveryOut(
        source="BiznesRadar",
        source_url=result.source_url,
        as_of=result.fetched_at,
        universe_count=len(result.candidates),
        result_count=len(candidates),
        source_note=result.source_note,
        candidates=candidates,
    )
