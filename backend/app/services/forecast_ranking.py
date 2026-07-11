"""Deterministic two-year analyst-consensus growth ranking for Discover."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Company, DocumentVersion, Fact, SourceDocument

RANKING_METRICS = ("revenue", "ebitda", "operating_profit", "net_income")
PROFIT_METRICS = {"ebitda", "operating_profit", "net_income"}
FORECAST_EXTRACTOR_VERSION = "biznesradar-forecasts@1"
MAX_SOURCE_AGE_DAYS = 7


def build_forecast_growth_ranking(
    db: Session,
    *,
    limit: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    cutoff_now = now or datetime.now(timezone.utc)
    if cutoff_now.tzinfo is None:
        cutoff_now = cutoff_now.replace(tzinfo=timezone.utc)
    documents = db.execute(
        select(Company, SourceDocument)
        .join(SourceDocument, SourceDocument.company_id == Company.id)
        .where(
            SourceDocument.source_type == "analyst_forecast",
            SourceDocument.scope_key == "consensus",
        )
        .order_by(Company.ticker)
    ).all()
    ranked: list[dict[str, Any]] = []
    insufficient = 0
    stale = 0
    for company, document in documents:
        version = _latest_parsed_version(db, document.id)
        if version is None:
            insufficient += 1
            continue
        fetched_at = _aware_utc(version.fetched_at)
        if fetched_at < cutoff_now - timedelta(days=MAX_SOURCE_AGE_DAYS):
            stale += 1
            continue
        item = _company_growth(
            db,
            company,
            document,
            version,
            current_year=cutoff_now.year,
        )
        if item is None:
            insufficient += 1
            continue
        ranked.append(item)
    ranked.sort(
        key=lambda item: (
            -item["composite_growth_pct"],
            -item["metric_coverage"],
            item["ticker"],
        )
    )
    for position, item in enumerate(ranked, start=1):
        item["rank"] = position
    return {
        "status": "research_shortlist",
        "method": "mean of valid adjacent-year metric growth rates, each capped to [-100%, 200%]",
        "universe": "fresh immutable BiznesRadar analyst-forecast versions",
        "universe_count": len(documents),
        "ranked_count": len(ranked),
        "insufficient_count": insufficient,
        "stale_count": stale,
        "fresh_after_days": MAX_SOURCE_AGE_DAYS,
        "analyst_count_available": False,
        "caveats": [
            "BiznesRadar consensus includes only forecasts not older than six months.",
            "The page does not expose analyst count in the stored table; coverage remains unknown.",
            "Only adjacent current/future years from one fresh immutable source version are compared.",
            "Negative-to-positive is a turnaround; continuing losses never enter percentage ranking.",
            "This is a research shortlist, not an investment recommendation.",
        ],
        "candidates": ranked[: max(1, min(limit, 100))],
    }


def _company_growth(
    db: Session,
    company: Company,
    document: SourceDocument,
    version: DocumentVersion,
    *,
    current_year: int,
) -> dict[str, Any] | None:
    facts = db.scalars(
        select(Fact).where(
            Fact.source_version_id == version.id,
            Fact.fact_type == "analyst_forecast",
            Fact.extractor_version == FORECAST_EXTRACTOR_VERSION,
        )
    ).all()
    values: dict[str, dict[str, float]] = {}
    for fact in facts:
        if fact.unit != "tys. PLN" or not fact.fact_key.startswith("forecast."):
            continue
        metric = fact.fact_key.removeprefix("forecast.")
        if metric not in RANKING_METRICS or not str(fact.period).isdigit():
            continue
        value = _finite_float(fact.numeric_value)
        if value is not None:
            values.setdefault(str(fact.period), {})[metric] = value
    years = sorted((int(year) for year in values if int(year) >= current_year))
    pair = next(
        ((year, year + 1) for year in years if year + 1 in years),
        None,
    )
    if pair is None:
        return None
    first_year_int, second_year_int = pair
    first_year, second_year = str(first_year_int), str(second_year_int)
    metrics: dict[str, dict[str, Any]] = {}
    valid_growth: list[float] = []
    for metric in RANKING_METRICS:
        first = values.get(first_year, {}).get(metric)
        second = values.get(second_year, {}).get(metric)
        growth = None
        transition = "unknown"
        if first is not None and second is not None:
            if first > 0:
                growth = round((second / first - 1) * 100, 2)
                valid_growth.append(max(-100.0, min(200.0, growth)))
                transition = "normal"
            elif first <= 0 < second:
                transition = "turnaround"
            elif first < second <= 0:
                transition = "loss_narrowing"
            else:
                transition = "deterioration"
        metrics[metric] = {
            "first_value": first,
            "second_value": second,
            "growth_pct": growth,
            "turnaround": transition == "turnaround",
            "transition": transition,
        }
    if metrics["revenue"]["growth_pct"] is None or not any(
        metrics[name]["growth_pct"] is not None for name in PROFIT_METRICS
    ):
        return None
    return {
        "rank": 0,
        "ticker": company.ticker,
        "name": company.name,
        "first_forecast_year": first_year,
        "second_forecast_year": second_year,
        "composite_growth_pct": round(mean(valid_growth), 2),
        "metric_coverage": len(valid_growth),
        "metrics": metrics,
        "analyst_count": None,
        "source": "biznesradar_forecasts",
        "source_version_id": version.id,
        "source_url": version.effective_url or document.canonical_url,
        "fetched_at": _aware_utc(version.fetched_at),
        "freshness_status": "fresh",
    }


def _latest_parsed_version(db: Session, document_id: int) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.source_document_id == document_id,
            DocumentVersion.parse_status == "parsed",
        )
        .order_by(DocumentVersion.fetched_at.desc(), DocumentVersion.id.desc())
        .limit(1)
    )


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
