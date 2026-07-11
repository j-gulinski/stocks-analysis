"""Stored market candidate sieve plus one explicit refresh command."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    DiscoveryCandidateOut,
    DiscoveryOut,
)
from app.db.base import get_db
from app.scrapers.biznesradar import ParseError
from app.services.discovery import discover_candidates, stored_discovery_candidates

router = APIRouter(prefix="/discovery", tags=["discovery"])

_RATING_RANK = {
    "AAA": 16,
    "AA+": 15,
    "AA": 14,
    "AA-": 13,
    "A+": 12,
    "A": 11,
    "A-": 10,
    "BBB+": 9,
    "BBB": 8,
    "BBB-": 7,
    "BB+": 6,
    "BB": 5,
    "BB-": 4,
    "B+": 3,
    "B": 2,
    "B-": 1,
}

_RECALL_MIN_RATING = 5.0


def _sort_key(candidate) -> tuple:
    return (
        -_RATING_RANK.get(candidate.rating or "", 0),
        -(
            candidate.piotroski_f_score
            if candidate.piotroski_f_score is not None
            else -1
        ),
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


def _rank_basis(candidate, rank: int, total: int) -> list[str]:
    f_score = (
        f"Jakość zmian w wynikach: {candidate.piotroski_f_score}/9 pozytywnych "
        "sygnałów Piotroskiego."
        if candidate.piotroski_f_score is not None
        else "Brak danych o jakości zmian w wynikach; kryterium pozostaje luką."
    )
    return [
        f"Pozycja {rank}/{total} w sicie kondycji finansowej.",
        "Kolejność: klasa odporności finansowej, jakość zmian w wynikach, wartość modelu, ticker.",
        (
            "Odporność finansowa według modelu Altmana: "
            f"{candidate.rating_value if candidate.rating_value is not None else 'b/d'} "
            f"(klasa {candidate.rating or 'brak'})."
        ),
        f_score,
    ]


def _discovery_out(
    result, *, min_rating: float, min_f_score: int | None, limit: int
) -> DiscoveryOut:
    selected = _select_candidates(
        result.candidates,
        min_rating=min_rating,
        min_f_score=min_f_score,
    )
    candidates = []
    selected_page = selected[:limit]
    for rank, candidate in enumerate(selected_page, start=1):
        reasons = [
            "Odporność finansowa: "
            f"{candidate.rating_value:g} (klasa {candidate.rating})"
        ]
        if candidate.piotroski_f_score is not None:
            reasons.append(
                "Jakość zmian w wynikach: "
                f"{candidate.piotroski_f_score}/9 pozytywnych sygnałów"
            )
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
                    "Brak danych o jakości zmian w wynikach; czynnik pozostaje luką."
                    if candidate.piotroski_f_score is None
                    else "To wyłącznie wstępne sito kondycji, nie ocena inwestycyjna."
                ),
            )
        )
    return DiscoveryOut(
        source="BiznesRadar",
        source_url=result.source_url,
        as_of=result.fetched_at,
        universe_count=len(result.candidates),
        result_count=len(candidates),
        source_note=result.source_note,
        source_version_id=result.source_version_id,
        candidates=candidates,
    )


def _parse_error(exc: ParseError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "BiznesRadar discovery wymaga uwagi: zapisany widok rankingu "
            f"nie został rozpoznany ({exc}). Sprawdź stan źródła lub fixture parsera."
        ),
    )


@router.get("", response_model=DiscoveryOut)
def list_candidates(
    min_rating: float = Query(default=_RECALL_MIN_RATING, ge=-1000, le=1000),
    min_f_score: int | None = Query(default=None, ge=0, le=9),
    limit: int = Query(default=300, ge=1, le=300),
    db: Session = Depends(get_db),
) -> DiscoveryOut:
    """Serve only stored evidence; a read never fetches, writes or queues."""
    try:
        result = stored_discovery_candidates(db)
    except ParseError as exc:
        raise _parse_error(exc) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brak zapisanego Discover. Najpierw uruchom jawne odświeżenie.",
        )
    return _discovery_out(
        result, min_rating=min_rating, min_f_score=min_f_score, limit=limit
    )


@router.post("/refresh", response_model=DiscoveryOut)
def refresh_candidates(
    min_rating: float = Query(default=_RECALL_MIN_RATING, ge=-1000, le=1000),
    min_f_score: int | None = Query(default=None, ge=0, le=9),
    limit: int = Query(default=300, ge=1, le=300),
    db: Session = Depends(get_db),
) -> DiscoveryOut:
    """Explicitly fetch and persist one fresh market-rating snapshot."""
    try:
        result = discover_candidates(db, force=True)
    except ParseError as exc:
        raise _parse_error(exc) from exc
    return _discovery_out(
        result, min_rating=min_rating, min_f_score=min_f_score, limit=limit
    )
