"""The one stored, exclusion-first ``workbench_sieve_v1``."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import DiscoveryOut, DiscoverySieveOut
from app.db.base import get_db
from app.scrapers import http as polite_http
from app.scrapers.biznesradar import ParseError
from app.services.discovery import (
    DISCOVERY_RESULT_LIMIT,
    batch_freshness,
    batch_sources,
    evaluate_batch,
    factor_source_versions,
    refresh_market_factor_batch,
    stored_market_factor_batch,
)
from app.services.workbench_sieve import SIEVE_ID, SIEVE_VERSION, rules

router = APIRouter(prefix="/discovery", tags=["discovery"])

_STALE_AFTER = timedelta(days=7)
_FACTOR_LABELS = {
    "altman_em_score": "Altman EM-Score",
    "piotroski_f_score": "Piotroski F-Score",
    "equity": "Kapitał własny",
    "revenue_growth": "Dynamika przychodów r/r",
    "net_income_growth": "Dynamika zysku netto r/r",
    "operating_margin": "Marża operacyjna",
    "operating_margin_change": "Zmiana marży operacyjnej",
    "net_debt_ebitda": "Dług netto / EBITDA",
    "net_income": "Zysk netto TTM",
    "turnover": "Obrót w oknie snapshotu",
    "current_pe": "C/Z bieżące",
    "valuation_vs_own_history": "C/Z względem własnej historii",
    "net_cash_or_debt_trend": "Gotówka netto / trend długu",
}


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _freshness(raw: dict) -> dict:
    content_at = _as_utc(raw["content_version_at"])
    last_check_at = _as_utc(raw["last_successful_source_check_at"])
    return {
        "status": "stale" if datetime.now(timezone.utc) - last_check_at > _STALE_AFTER else "current",
        "content_version_at": content_at,
        "last_successful_source_check_at": last_check_at,
        "last_failed_refresh_at": raw["last_failed_refresh_at"],
        "last_failed_refresh_reason": raw["last_failed_refresh_reason"],
        "stale_after_hours": int(_STALE_AFTER.total_seconds() // 3600),
    }


def _factors(items, source_by_factor: dict[str, dict], freshness: dict) -> list[dict]:
    result: list[dict] = []
    for item in items:
        source = source_by_factor.get(item.id)
        result.append(
            {
                "id": item.id,
                "label": item.label,
                "note": item.note,
                "value": item.value,
                "delta": item.delta,
                "period": item.period,
                "source_document_version_id": (
                    source["document_version_id"] if source is not None else None
                ),
                "source_as_of": source["as_of"] if source is not None else None,
                "source_freshness": freshness["status"] if source is not None else None,
                "history_median": item.history_median,
                "history_batch_ids": list(item.history_batch_ids),
                "history_document_version_ids": list(item.history_document_version_ids),
            }
        )
    return result


def _out(db: Session, batch) -> DiscoveryOut:
    outcome = evaluate_batch(db, batch)
    visible_candidates = outcome.candidates[:DISCOVERY_RESULT_LIMIT]
    freshness = _freshness(batch_freshness(db, batch))
    sources = batch_sources(db, batch)
    source_by_factor = factor_source_versions(db, batch)
    total = len(outcome.candidates) + len(outcome.excluded)
    coverage = [
        {
            "id": factor_id,
            "label": _FACTOR_LABELS[factor_id],
            "covered_count": outcome.factor_coverage[factor_id],
            "total_count": total,
        }
        for factor_id in _FACTOR_LABELS
    ]
    gaps = [
        "Brak źródła obrotu: A6 pozostaje widocznym niepokrytym warunkiem.",
        "Brak punktowego zysku netto TTM: A7 pozostaje widocznym niepokrytym warunkiem.",
        "Brak wartości długu netto i jego zmiany: B5 nie jest syntetyzowany ze wskaźnika.",
    ]
    if outcome.factor_coverage["valuation_vs_own_history"] == 0:
        gaps.append(
            "Brak snapshotu C/Z starszego o co najmniej 30 dni: B4 pozostaje "
            "nieaktywny do zbudowania rzeczywistej historii."
        )
    scoreable_count = sum(item.potential_score is not None for item in outcome.candidates)
    if scoreable_count < len(outcome.candidates):
        gaps.append(
            "Porównywalny wynik potencjału ma "
            f"{scoreable_count}/{len(outcome.candidates)} spółek, które przeszły sito; "
            "brakujących składników nie imputowano."
        )
    sieve = DiscoverySieveOut(
        id=SIEVE_ID,
        version=SIEVE_VERSION,
        title="Sito Workbench",
        question="Które spółki nie odpadają i pokazują realną poprawę?",
        status="available",
        universe_count=total,
        survivor_count=len(outcome.candidates),
        excluded_count=len(outcome.excluded),
        coverage_count=outcome.coverage_count,
        coverage_pct=round((outcome.coverage_count / total * 100.0), 1) if total else 0.0,
        coverage_label="Dane bazowe A1–A5 oraz B1–B3 (bez niepokrytych A6/A7/B4/B5).",
        rules=rules(),
        factor_coverage=coverage,
        batch_id=batch.id,
        sources=sources,
        freshness=freshness,
        gaps=gaps,
    )
    return DiscoveryOut(
        as_of=_as_utc(batch.as_of),
        universe_count=total,
        result_count=len(visible_candidates),
        source_note=(
            "Jedno sito korzysta wyłącznie z kompletnego, niemutowalnego batcha "
            "rynkowych stron BiznesRadar. Pokazuje maksymalnie 100 spółek według "
            "porównywalnego wyniku potencjału; brak czynnika pozostaje widoczny."
        ),
        freshness=freshness,
        sieve=sieve,
        candidates=[
            {
                "ticker": item.ticker,
                "name": item.name,
                "rank": item.rank,
                "rank_basis": list(item.rank_basis),
                "factors": _factors(item.factors, source_by_factor, freshness),
                "factor_gaps": list(item.factor_gaps),
                "improvement_signals": list(item.improvement_signals),
                "potential_score": item.potential_score,
                "score_components": [
                    {
                        "id": component.id,
                        "label": component.label,
                        "raw_value": component.raw_value,
                        "ranking_value": component.ranking_value,
                        "percentile": component.percentile,
                        "weight": component.weight,
                    }
                    for component in item.score_components
                ],
            }
            for item in visible_candidates
        ],
        excluded=[
            {
                "ticker": item.ticker,
                "name": item.name,
                "kill_reasons": list(item.kill_reasons),
                "factors": _factors(item.factors, source_by_factor, freshness),
                "factor_gaps": list(item.factor_gaps),
            }
            for item in outcome.excluded
        ],
    )


def _parse_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Discover wymaga uwagi: zapisane źródło nie zostało rozpoznane "
            f"({exc}). Poprzedni kompletny batch pozostaje dostępny."
        ),
    )


def _source_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Discover wymaga uwagi: ostatnie odświeżenie źródła nie powiodło "
            f"się ({exc}). Poprzedni kompletny batch pozostaje dostępny."
        ),
    )


@router.get("", response_model=DiscoveryOut)
def list_candidates(db: Session = Depends(get_db)) -> DiscoveryOut:
    """Stored read only: no fetch, database write or job creation."""
    batch = stored_market_factor_batch(db)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brak kompletnego batcha Discover. Uruchom jawne odświeżenie źródeł.",
        )
    try:
        return _out(db, batch)
    except ParseError as exc:
        raise _parse_error(exc) from exc


@router.post("/refresh", response_model=DiscoveryOut)
def refresh_candidates(db: Session = Depends(get_db)) -> DiscoveryOut:
    """Explicit command; publishes only an all-page immutable factor batch."""
    try:
        batch = refresh_market_factor_batch(db, force=True)
        return _out(db, batch)
    except ParseError as exc:
        raise _parse_error(exc) from exc
    except (polite_http.FetchError, LookupError) as exc:
        raise _source_error(exc) from exc
