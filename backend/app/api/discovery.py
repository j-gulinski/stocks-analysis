"""The single stored Workbench sieve plus one explicit refresh command.

The legacy rating page is retained as immutable source evidence, but it is not
enough to execute ``workbench_sieve_v1``. Until the expanded market-factor
batch exists, the API exposes one blocked sieve with computed coverage gaps and
no fabricated survivors or exclusions (VISION V1, V9).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import DiscoveryOut, DiscoverySieveOut
from app.db.base import get_db
from app.scrapers import http as polite_http
from app.scrapers.biznesradar import ParseError
from app.services.discovery import (
    PARSER_VERSION,
    discover_candidates,
    stored_discovery_candidates,
)

router = APIRouter(prefix="/discovery", tags=["discovery"])

_SIEVE_ID = "workbench_sieve_v1"
_SIEVE_VERSION = "workbench-sieve-v1"
_STALE_AFTER = timedelta(days=7)


def _freshness(result) -> dict:
    content_at = getattr(result, "content_version_at", result.fetched_at)
    last_check_at = getattr(result, "last_successful_source_check_at", content_at)
    if content_at.tzinfo is None:
        content_at = content_at.replace(tzinfo=timezone.utc)
    if last_check_at.tzinfo is None:
        last_check_at = last_check_at.replace(tzinfo=timezone.utc)
    return {
        "status": (
            "stale"
            if datetime.now(timezone.utc) - last_check_at > _STALE_AFTER
            else "current"
        ),
        "content_version_at": content_at,
        "last_successful_source_check_at": last_check_at,
        "last_failed_refresh_at": getattr(result, "last_failed_refresh_at", None),
        "last_failed_refresh_reason": getattr(
            result, "last_failed_refresh_reason", None
        ),
        "stale_after_hours": int(_STALE_AFTER.total_seconds() // 3600),
    }


def _source(result) -> dict:
    return {
        "name": "BiznesRadar",
        "version": str(result.source_version_id),
        "document_version_id": result.source_version_id,
        "parser_version": getattr(result, "parser_version", PARSER_VERSION),
        "as_of": result.fetched_at,
    }


def _factor_coverage(result) -> list[dict]:
    universe = len(result.candidates)
    altman = sum(
        row.rating is not None and row.rating_value is not None
        for row in result.candidates
    )
    piotroski = sum(
        row.piotroski_f_score is not None for row in result.candidates
    )
    return [
        {
            "id": "altman_em_score",
            "label": "Altman EM-Score",
            "covered_count": altman,
            "total_count": universe,
        },
        {
            "id": "piotroski_f_score",
            "label": "Piotroski F-Score",
            "covered_count": piotroski,
            "total_count": universe,
        },
        {
            "id": "revenue_and_margin_trend",
            "label": "Dynamika przychodów i marży operacyjnej",
            "covered_count": 0,
            "total_count": universe,
        },
        {
            "id": "valuation_vs_own_history",
            "label": "Wycena względem własnej historii",
            "covered_count": 0,
            "total_count": universe,
        },
        {
            "id": "debt_and_cash",
            "label": "Dług i gotówka",
            "covered_count": 0,
            "total_count": universe,
        },
        {
            "id": "turnover",
            "label": "Płynność obrotu",
            "covered_count": 0,
            "total_count": universe,
        },
    ]


def _rules() -> list[dict]:
    return [
        {
            "layer": "hard_kill",
            "factor_id": "altman_em_score",
            "label": "Strefa zagrożenia wypłacalności",
            "operator": "lt",
            "threshold": 4.0,
        },
        {
            "layer": "hard_kill",
            "factor_id": "piotroski_f_score",
            "label": "Zapaść jakości finansowej",
            "operator": "lte",
            "threshold": 3.0,
        },
        {
            "layer": "hard_kill",
            "factor_id": "revenue_and_margin_trend",
            "label": "Jednoczesny regres przychodów i marży",
            "operator": "composite",
        },
        {
            "layer": "hard_kill",
            "factor_id": "debt_and_cash",
            "label": "Ekstremalna dźwignia",
            "operator": "gt",
            "threshold": 6.0,
        },
        {
            "layer": "improvement",
            "factor_id": "improvement_signals",
            "label": "Co najmniej dwa sygnały poprawy",
            "operator": "gte",
            "threshold": 2.0,
        },
    ]


def _discovery_out(result) -> DiscoveryOut:
    universe = len(result.candidates)
    freshness = _freshness(result)
    gaps = [
        "Brak kompletnego, wersjonowanego batcha czynników rynkowych.",
        "Brak rynkowego pokrycia trendu przychodów i marży operacyjnej.",
        "Brak porównania wyceny spółek z ich własną historią.",
        "Brak rynkowego pokrycia długu, gotówki i płynności obrotu.",
    ]
    sieve = DiscoverySieveOut(
        id=_SIEVE_ID,
        version=_SIEVE_VERSION,
        title="Sito Workbench",
        question="Które spółki nie odpadają i pokazują realną poprawę?",
        status="blocked",
        universe_count=universe,
        survivor_count=0,
        excluded_count=0,
        coverage_count=0,
        coverage_pct=0.0,
        rules=_rules(),
        factor_coverage=_factor_coverage(result),
        source=_source(result),
        freshness=freshness,
        gaps=gaps,
    )
    return DiscoveryOut(
        source="BiznesRadar",
        source_url=result.source_url,
        as_of=result.fetched_at,
        universe_count=universe,
        result_count=0,
        source_note=(
            f"{result.source_note} Zapisana strona ratingowa jest tylko częścią "
            "wymaganego batcha Workbench."
        ),
        source_version_id=result.source_version_id,
        freshness=freshness,
        sieve=sieve,
        candidates=[],
        excluded=[],
    )


def _parse_error(exc: ParseError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Discover wymaga uwagi: zapisane źródło nie zostało rozpoznane "
            f"({exc}). Sprawdź stan źródła lub fixture parsera."
        ),
    )


def _source_error(exc: polite_http.FetchError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Discover wymaga uwagi: ostatnie odświeżenie źródła nie powiodło "
            f"się ({exc}). Ostatni poprawny zapis pozostaje dostępny."
        ),
    )


@router.get("", response_model=DiscoveryOut)
def list_candidates(db: Session = Depends(get_db)) -> DiscoveryOut:
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
    return _discovery_out(result)


@router.post("/refresh", response_model=DiscoveryOut)
def refresh_candidates(db: Session = Depends(get_db)) -> DiscoveryOut:
    """Explicitly refresh the retained rating source for future S1 ingestion."""
    try:
        result = discover_candidates(db, force=True)
    except ParseError as exc:
        raise _parse_error(exc) from exc
    except polite_http.FetchError as exc:
        raise _source_error(exc) from exc
    return _discovery_out(result)
