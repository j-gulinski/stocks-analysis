"""Stored market candidate sieve plus one explicit refresh command."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    DiscoveryCandidateOut,
    DiscoveryOut,
    DiscoverySieveOut,
)
from app.db.base import get_db
from app.scrapers import http as polite_http
from app.scrapers.biznesradar import ParseError
from app.services.discovery import (
    PARSER_VERSION,
    discover_candidates,
    stored_discovery_candidates,
)

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

_FINANCIAL_MIN_RATING = 8.0
_FINANCIAL_MIN_F_SCORE = 7
_STALE_AFTER = timedelta(days=7)
_MAX_REPORT_AGE_QUARTERS = 2
_FINANCIAL_SIEVE_ID = "financial_health_br_v1"
_FINANCIAL_SIEVE_VERSION = "financial-health-br-v1"


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


def _rank_basis(candidate, rank: int | None, total: int) -> list[str]:
    f_score = (
        f"Jakość zmian w wynikach: {candidate.piotroski_f_score}/9 pozytywnych "
        "sygnałów Piotroskiego."
        if candidate.piotroski_f_score is not None
        else "Brak danych o jakości zmian w wynikach; kryterium pozostaje luką."
    )
    return [
        (
            f"Pozycja {rank}/{total} w sicie kondycji finansowej."
            if rank is not None
            else "Dane są nieaktualne; kolejność nie jest bieżącą pozycją w sicie."
        ),
        "Kolejność: klasa odporności finansowej, jakość zmian w wynikach, wartość modelu, ticker.",
        (
            "Odporność finansowa według modelu Altmana: "
            f"{candidate.rating_value if candidate.rating_value is not None else 'b/d'} "
            f"(klasa {candidate.rating or 'brak'})."
        ),
        f_score,
    ]


def _freshness(result):
    content_at = getattr(result, "content_version_at", result.fetched_at)
    last_check_at = getattr(result, "last_successful_source_check_at", content_at)
    if content_at.tzinfo is None:
        content_at = content_at.replace(tzinfo=timezone.utc)
    if last_check_at.tzinfo is None:
        last_check_at = last_check_at.replace(tzinfo=timezone.utc)
    status_name = "stale" if datetime.now(timezone.utc) - last_check_at > _STALE_AFTER else "current"
    return {
        "status": status_name,
        "content_version_at": content_at,
        "last_successful_source_check_at": last_check_at,
        "last_failed_refresh_at": getattr(result, "last_failed_refresh_at", None),
        "last_failed_refresh_reason": getattr(result, "last_failed_refresh_reason", None),
        "stale_after_hours": int(_STALE_AFTER.total_seconds() // 3600),
    }


def _report_period_is_stale(report_period: str, *, as_of: datetime) -> bool:
    try:
        year = int(report_period[:4])
        quarter = int(report_period[-1])
    except (TypeError, ValueError):
        return True
    current_quarter = (as_of.month - 1) // 3 + 1
    age = (as_of.year - year) * 4 + current_quarter - quarter
    return age > _MAX_REPORT_AGE_QUARTERS


def _neutral_context() -> list[dict]:
    return [
        {
            "id": "wig_bucket",
            "label": "Indeks WIG",
            "value": None,
            "basis": "Brak w zapisanym źródle rynkowego ratingu.",
        },
        {
            "id": "sector",
            "label": "Sektor",
            "value": None,
            "basis": "Brak w zapisanym źródle rynkowego ratingu.",
        },
        {
            "id": "size",
            "label": "Wielkość",
            "value": None,
            "basis": "Brak raportowanej kapitalizacji w zapisanym źródle rynkowego ratingu.",
        },
    ]


def _strategy_questions() -> list[str]:
    return [
        "Jaki mechanizm może poprawić wyniki w kolejnym kwartale lub roku?",
        "Czy wynik bazowy i przepływy pieniężne potwierdzają jakość poprawy?",
        "Jaki katalizator i falsyfikator uzasadniają dalszy Research?",
    ]


def _financial_source(result) -> dict:
    return {
        "name": "BiznesRadar",
        "version": str(result.source_version_id),
        "document_version_id": result.source_version_id,
        "parser_version": getattr(result, "parser_version", PARSER_VERSION),
        "as_of": result.fetched_at,
    }


def _financial_membership(candidate, *, rank: int, total: int, current: bool, source: dict, freshness: dict) -> dict:
    factors_current = current and not _report_period_is_stale(
        candidate.report_period, as_of=freshness["last_successful_source_check_at"]
    )
    return {
        "sieve_id": _FINANCIAL_SIEVE_ID,
        "sieve_version": _FINANCIAL_SIEVE_VERSION,
        "rank": rank if factors_current else None,
        "rank_basis": _rank_basis(candidate, rank if factors_current else None, total),
        "factor_status": "current" if factors_current else "stale",
        "factors": [
            {
                "id": "altman_em_score",
                "label": "Wartość Altman EM-Score",
                "note": "Kondycja finansowa według modelu Altmana.",
                "value": candidate.rating_value,
                "report_period": candidate.report_period,
                "source_document_version_id": source["document_version_id"],
            },
            {
                "id": "piotroski_f_score",
                "label": "Piotroski F-Score",
                "note": "Zmiany rentowności, płynności i efektywności.",
                "value": candidate.piotroski_f_score,
                "report_period": candidate.report_period,
                "source_document_version_id": source["document_version_id"],
            },
        ],
        "factor_gaps": (
            ["Brak F-Score Piotroskiego w zapisanym źródle."]
            if candidate.piotroski_f_score is None
            else []
        ),
        "strategy_questions": _strategy_questions(),
        "caveat": (
            "Czynniki pochodzą ze starego okresu raportowego; kolejność nie jest bieżąca."
            if current and not factors_current
            else "Dane są nieaktualne; odśwież źródło przed traktowaniem listy jako bieżącej."
            if not current
            else "To wyłącznie wstępne sito kondycji, nie ocena inwestycyjna."
        ),
        "source": source,
        "freshness": freshness,
    }


def _candidate_union(entries: list[tuple[object, dict]]) -> list[DiscoveryCandidateOut]:
    """Merge per-sieve membership records without creating a global rank."""
    grouped: dict[str, tuple[object, list[dict]]] = {}
    for candidate, membership in entries:
        stored = grouped.get(candidate.ticker)
        if stored is None:
            grouped[candidate.ticker] = (candidate, [membership])
        else:
            stored[1].append(membership)
    return [
        DiscoveryCandidateOut(
            ticker=ticker,
            name=candidate.name,
            neutral_context=_neutral_context(),
            memberships=memberships,
            overlap={
                "sieve_ids": [membership["sieve_id"] for membership in memberships],
                "count": len(memberships),
            },
        )
        for ticker, (candidate, memberships) in grouped.items()
    ]


def _compose_discovery_out(
    result,
    *,
    candidate_entries: list[tuple[object, dict]],
    sieves: list[DiscoverySieveOut],
) -> DiscoveryOut:
    """Build one union response from independently sourced sieve memberships."""
    candidates = _candidate_union(candidate_entries)
    memberships_by_ticker = {
        candidate.ticker: {membership.sieve_id for membership in candidate.memberships}
        for candidate in candidates
    }
    for sieve in sieves:
        referenced = {reference.ticker for reference in sieve.candidates}
        expected = {
            ticker
            for ticker, membership_ids in memberships_by_ticker.items()
            if sieve.id in membership_ids
        }
        if referenced != expected:
            raise ValueError(
                f"Sieve {sieve.id} candidate references do not match its memberships."
            )
    return DiscoveryOut(
        source="BiznesRadar",
        source_url=result.source_url,
        as_of=result.fetched_at,
        universe_count=len(result.candidates),
        result_count=len(candidates),
        source_note=result.source_note,
        source_version_id=result.source_version_id,
        freshness=_freshness(result),
        candidates=candidates,
        sieves=sieves,
    )


def _discovery_out(result, *, limit: int) -> DiscoveryOut:
    selected = _select_candidates(
        result.candidates,
        min_rating=_FINANCIAL_MIN_RATING,
        min_f_score=_FINANCIAL_MIN_F_SCORE,
    )
    universe_count = len(result.candidates)
    altman_count = sum(
        item.rating is not None and item.rating_value is not None
        for item in result.candidates
    )
    piotroski_count = sum(
        item.piotroski_f_score is not None for item in result.candidates
    )
    joint_count = sum(
        item.rating is not None
        and item.rating_value is not None
        and item.piotroski_f_score is not None
        for item in result.candidates
    )
    freshness = _freshness(result)
    source_current = freshness["status"] == "current"
    source = _financial_source(result)
    candidate_entries = []
    financial_refs = []
    selected_page = selected[:limit]
    for rank, candidate in enumerate(selected_page, start=1):
        membership = _financial_membership(
            candidate,
            rank=rank,
            total=len(selected),
            current=source_current,
            source=source,
            freshness=freshness,
        )
        candidate_entries.append((candidate, membership))
        financial_refs.append({"ticker": candidate.ticker})
    return _compose_discovery_out(
        result,
        candidate_entries=candidate_entries,
        sieves=_sieves(
            result,
            universe_count=universe_count,
            selected_count=len(selected),
            altman_count=altman_count,
            piotroski_count=piotroski_count,
            joint_count=joint_count,
            financial_source=source,
            financial_freshness=freshness,
            financial_candidates=financial_refs,
        ),
    )


def _pct(covered: int, total: int) -> float:
    return round((covered / total) * 100, 1) if total else 0.0


def _sieves(
    result,
    *,
    universe_count: int,
    selected_count: int,
    altman_count: int,
    piotroski_count: int,
    joint_count: int,
    financial_source: dict,
    financial_freshness: dict,
    financial_candidates: list[dict],
) -> list[DiscoverySieveOut]:
    financial_gaps = []
    if altman_count < universe_count:
        financial_gaps.append(
            f"Brak klasy lub wartości Altmana dla {universe_count - altman_count} spółek."
        )
    if piotroski_count < universe_count:
        financial_gaps.append(
            f"Brak F-Score Piotroskiego dla {universe_count - piotroski_count} spółek."
        )
    return [
        DiscoverySieveOut(
            id=_FINANCIAL_SIEVE_ID,
            version=_FINANCIAL_SIEVE_VERSION,
            title="Kondycja finansowa",
            question="Które spółki łączą odporność finansową z poprawą jakości wyników?",
            status="available",
            universe_count=universe_count,
            candidate_count=selected_count,
            coverage_count=joint_count,
            coverage_pct=_pct(joint_count, universe_count),
            selection_rules=[
                {
                    "factor_id": "altman_em_score",
                    "label": "Wartość Altman EM-Score",
                    "operator": "gte",
                    "threshold": _FINANCIAL_MIN_RATING,
                },
                {
                    "factor_id": "piotroski_f_score",
                    "label": "Piotroski F-Score",
                    "operator": "gte",
                    "threshold": _FINANCIAL_MIN_F_SCORE,
                },
            ],
            factor_coverage=[
                {
                    "id": "altman_em_score",
                    "label": "Kondycja finansowa (Altman EM-Score)",
                    "covered_count": altman_count,
                    "total_count": universe_count,
                },
                {
                    "id": "piotroski_f_score",
                    "label": "Jakość zmian w wynikach (Piotroski F-Score)",
                    "covered_count": piotroski_count,
                    "total_count": universe_count,
                },
            ],
            source=financial_source,
            freshness=financial_freshness,
            candidates=financial_candidates,
            gaps=financial_gaps,
        ),
        DiscoverySieveOut(
            id="obs_operating_improvement_v1",
            version="obs-operating-improvement-v1",
            title="Wyniki i katalizator",
            question="Gdzie poprawa operacyjna może przełożyć się na kolejne kwartały?",
            status="blocked",
            universe_count=universe_count,
            candidate_count=0,
            coverage_count=0,
            coverage_pct=0.0,
            selection_rules=[],
            factor_coverage=[
                {"id": "revenue_driver", "label": "Trend i motor przychodów", "covered_count": 0, "total_count": universe_count},
                {"id": "margin_leverage", "label": "Marża i dźwignia operacyjna", "covered_count": 0, "total_count": universe_count},
                {"id": "core_result", "label": "Wynik bazowy bez zdarzeń jednorazowych", "covered_count": 0, "total_count": universe_count},
                {"id": "cash_balance", "label": "Gotówka, kapitał obrotowy i zadłużenie", "covered_count": 0, "total_count": universe_count},
                {"id": "valuation_history", "label": "Wycena względem własnej historii", "covered_count": 0, "total_count": universe_count},
                {"id": "catalyst", "label": "Katalizator i ocena oczekiwań rynku", "covered_count": 0, "total_count": universe_count},
            ],
            source=None,
            freshness=None,
            candidates=[],
            gaps=[
                "Brak jednego wersjonowanego, rynkowego zestawu trendów wyników, przepływów i wyceny.",
                "Katalizator i stopień uwzględnienia go w cenie wymagają osobnej, źródłowej oceny.",
            ],
        ),
        DiscoverySieveOut(
            id="pa_value_catalyst_v1",
            version="pa-value-catalyst-v1",
            title="Wartość i asymetria zdarzeń",
            question="Gdzie wycena i konkretne zdarzenie tworzą mierzalną asymetrię?",
            status="blocked",
            universe_count=universe_count,
            candidate_count=0,
            coverage_count=0,
            coverage_pct=0.0,
            selection_rules=[],
            factor_coverage=[
                {"id": "value_quality", "label": "Wycena, rentowność i bilans", "covered_count": 0, "total_count": universe_count},
                {"id": "normalized_result", "label": "Znormalizowany wynik i efekt bazy", "covered_count": 0, "total_count": universe_count},
                {"id": "capital_allocation", "label": "Dywidenda, skup i alokacja kapitału", "covered_count": 0, "total_count": universe_count},
                {"id": "owner_alignment", "label": "Ceny referencyjne właścicieli i wiarygodność zarządu", "covered_count": 0, "total_count": universe_count},
                {"id": "event_economics", "label": "Ekonomika zdarzenia", "covered_count": 0, "total_count": universe_count},
                {"id": "asymmetry", "label": "Mechanizm downside/upside i horyzont", "covered_count": 0, "total_count": universe_count},
            ],
            source=None,
            freshness=None,
            candidates=[],
            gaps=[
                "Brak wersjonowanego, rynkowego zestawu wyceny, jakości, bilansu i alokacji kapitału.",
                "Brak zachowanych źródeł metod Areczeks/Elendix wystarczających do twardej selekcji.",
                "Ekonomika zdarzeń i asymetria nie mogą być wywnioskowane z rankingu kondycji finansowej.",
            ],
        ),
    ]


def _parse_error(exc: ParseError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "BiznesRadar discovery wymaga uwagi: zapisany widok rankingu "
            f"nie został rozpoznany ({exc}). Sprawdź stan źródła lub fixture parsera."
        ),
    )


def _source_error(exc: polite_http.FetchError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "BiznesRadar discovery wymaga uwagi: ostatnie odświeżenie źródła "
            f"nie powiodło się ({exc}). Wyświetlone pozostają ostatnie poprawne dane."
        ),
    )


@router.get("", response_model=DiscoveryOut)
def list_candidates(
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
    return _discovery_out(result, limit=limit)


@router.post("/refresh", response_model=DiscoveryOut)
def refresh_candidates(
    limit: int = Query(default=300, ge=1, le=300),
    db: Session = Depends(get_db),
) -> DiscoveryOut:
    """Explicitly fetch and persist one fresh market-rating snapshot."""
    try:
        result = discover_candidates(db, force=True)
    except ParseError as exc:
        raise _parse_error(exc) from exc
    except polite_http.FetchError as exc:
        raise _source_error(exc) from exc
    return _discovery_out(result, limit=limit)
