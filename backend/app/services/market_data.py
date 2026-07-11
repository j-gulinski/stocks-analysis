"""AI-priority market data snapshot.

The scrape tables stay long/narrow, but the valuation prompt needs a compact
context row: industry type, premium metrics (ROIC/FCF/EV), forward consensus,
and dividend coverage from FCF. This service derives and upserts that row.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import Company, CompanyMarketData, Dividend, IndicatorValue, ReportValue
from app.services import fields, insights

# Caveat surfaced next to forecast_consensus in the dossier's market_data
# block (feeds both the AI prompt — see services/prompts.py, `market_data` is
# passed through verbatim — and, per the frontend contract, a UI note near
# the consensus table). BiznesRadar only counts analyst forecasts younger
# than 6 months, so small/mid-cap GPW names frequently show thin or entirely
# empty consensus columns — never treat a populated year as broad coverage.
FORECAST_CONSENSUS_NOTE = (
    "Konsensus analityków (BiznesRadar) — traktować ostrożnie: dla mniejszych "
    "spółek GPW pokrycie analityczne bywa znikome, a kolumny konsensusu "
    "często są puste lub oparte o pojedyncze prognozy."
)


def classify_industry_type(sector: str | None, sector_group: str | None = None) -> str:
    """Prompt-facing industry bucket."""
    lowered = (sector or "").lower()
    group = sector_group or insights.classify_sector(sector)
    if "gry" in lowered or "gier" in lowered or "gaming" in lowered:
        return "Gaming"
    if group == "realestate":
        return "Real Estate / Developers"
    if "saas" in lowered or "oprogramowanie" in lowered or "software" in lowered:
        return "SaaS"
    return insights.SECTOR_GROUP_LABELS.get(group, "Pozostałe")


def _latest_indicator(db: Session, company_id: int, code: str) -> dict | None:
    row = db.scalar(
        select(IndicatorValue)
        .where(
            IndicatorValue.company_id == company_id,
            IndicatorValue.indicator == code,
            IndicatorValue.value.is_not(None),
        )
        .order_by(IndicatorValue.period.desc())
        .limit(1)
    )
    if row is None:
        return None
    return {
        "value": float(row.value),
        "period": row.period,
        "source": f"indicator_values.{code}",
    }


def _latest_report_metric(db: Session, company_id: int, names: set[str]) -> dict | None:
    rows = db.scalars(
        select(ReportValue)
        .where(ReportValue.company_id == company_id, ReportValue.value.is_not(None))
        .order_by(ReportValue.period.desc(), ReportValue.scraped_at.desc())
    ).all()
    for row in rows:
        normalized = fields.normalize_label(row.field_label)
        code = fields.normalize_label(row.field_code or "")
        if normalized in names or code in names:
            return {
                "value": float(row.value),
                "period": row.period,
                "unit": "tys. PLN",
                "source": f"report_values.{row.statement}.{row.field_code}",
            }
    return None


def _latest_dividend_coverage(db: Session, company: Company, fcf: dict | None) -> dict:
    if fcf is None or fcf.get("value") is None or not company.shares_outstanding:
        return {
            "fcf_coverage_ratio": None,
            "status": "missing",
            "reason": "Brak FCF lub liczby akcji do pokrycia dywidendy z FCF.",
        }
    dividend = db.scalar(
        select(Dividend)
        .where(Dividend.company_id == company.id, Dividend.dps.is_not(None))
        .order_by(Dividend.year.desc())
        .limit(1)
    )
    if dividend is None:
        return {
            "fcf_coverage_ratio": None,
            "status": "missing",
            "reason": "Brak najnowszej dywidendy na akcję.",
        }

    dividend_cash_pln = float(dividend.dps) * int(company.shares_outstanding)
    if dividend_cash_pln <= 0:
        return {
            "fcf_coverage_ratio": None,
            "status": "missing",
            "reason": "Dywidenda gotówkowa nie jest dodatnia.",
        }
    fcf_pln = float(fcf["value"]) * 1000.0
    ratio = fcf_pln / dividend_cash_pln
    return {
        "fcf_coverage_ratio": ratio,
        "status": "covered" if ratio >= 1.0 else "not_covered",
        "dividend_year": dividend.year,
        "source": "FCF / (DPS * shares_outstanding)",
    }


def _has_value(item) -> bool:
    return isinstance(item, dict) and item.get("value") is not None


def _merge_existing_advanced(derived: dict, existing: CompanyMarketData | None) -> dict:
    if existing is None:
        return derived
    merged = dict(derived)
    for key, item in (existing.advanced_metrics or {}).items():
        if _has_value(item):
            merged[key] = item
    return merged


def build_snapshot(
    db: Session,
    company: Company,
    *,
    sector_group: str | None = None,
    existing: CompanyMarketData | None = None,
) -> dict:
    """Build a JSON-safe snapshot from stored rows."""
    industry_type = classify_industry_type(company.sector, sector_group)
    roic = _latest_indicator(db, company.id, "roic")
    fcf = _latest_indicator(db, company.id, "fcf") or _latest_report_metric(
        db,
        company.id,
        {
            "fcf",
            "free cash flow",
            "wolne przepływy pieniężne",
            "wolne przeplywy pieniezne",
        },
    )
    ev_value = (
        {"value": float(company.enterprise_value), "unit": "PLN", "source": "companies.enterprise_value"}
        if company.enterprise_value is not None
        else _latest_indicator(db, company.id, "ev")
    )
    advanced_metrics = _merge_existing_advanced(
        {"roic": roic, "fcf": fcf, "enterprise_value": ev_value}, existing
    )
    forecast_consensus = dict(existing.forecast_consensus or {}) if existing else {}
    dividend_coverage = _latest_dividend_coverage(db, company, advanced_metrics.get("fcf"))
    if existing is not None and (existing.dividend_coverage or {}).get("fcf_coverage_ratio") is not None:
        dividend_coverage = dict(existing.dividend_coverage)

    priority_values = {
        "industry_type": industry_type,
        "advanced_metrics": advanced_metrics,
        "forecast_consensus": forecast_consensus,
        "dividend_coverage": dividend_coverage,
    }
    return {
        "industry_type": industry_type,
        "priority_values": priority_values,
        "forecast_consensus": forecast_consensus,
        "advanced_metrics": advanced_metrics,
        "dividend_coverage": dividend_coverage,
    }


def upsert_company_market_data(
    db: Session, company: Company, *, sector_group: str | None = None
) -> CompanyMarketData:
    existing = db.scalar(
        select(CompanyMarketData).where(CompanyMarketData.company_id == company.id)
    )
    snapshot = build_snapshot(db, company, sector_group=sector_group, existing=existing)
    if existing is None:
        existing = CompanyMarketData(company_id=company.id, **snapshot)
        db.add(existing)
    else:
        for key, value in snapshot.items():
            setattr(existing, key, value)
    return existing


def merge_premium_market_data(db: Session, company: Company, premium: dict) -> None:
    """Merge parser output from authenticated BR pages into the priority row."""
    if not premium:
        return
    record = db.scalar(
        select(CompanyMarketData).where(CompanyMarketData.company_id == company.id)
    )
    if record is None:
        record = CompanyMarketData(
            company_id=company.id,
            industry_type=classify_industry_type(company.sector),
            priority_values={},
            forecast_consensus={},
            advanced_metrics={},
            dividend_coverage={},
        )
        db.add(record)

    forecast = dict(record.forecast_consensus or {})
    for year, metrics_for_year in (premium.get("forecast_consensus") or {}).items():
        forecast.setdefault(year, {}).update(metrics_for_year or {})
    advanced = dict(record.advanced_metrics or {})
    advanced.update(premium.get("advanced_metrics") or {})
    dividend = dict(record.dividend_coverage or {})
    dividend.update(premium.get("dividend_coverage") or {})

    record.forecast_consensus = forecast
    record.advanced_metrics = advanced
    record.dividend_coverage = dividend
    record.priority_values = {
        "industry_type": record.industry_type,
        "advanced_metrics": advanced,
        "forecast_consensus": forecast,
        "dividend_coverage": dividend,
    }
    for field_name in (
        "forecast_consensus",
        "advanced_metrics",
        "dividend_coverage",
        "priority_values",
    ):
        flag_modified(record, field_name)
    db.flush()


def replace_forecast_consensus(
    db: Session,
    company: Company,
    forecast_consensus: dict,
) -> None:
    """Replace one page snapshot so removed or empty years cannot survive."""
    record = db.scalar(
        select(CompanyMarketData).where(CompanyMarketData.company_id == company.id)
    )
    if record is None:
        record = CompanyMarketData(
            company_id=company.id,
            industry_type=classify_industry_type(company.sector),
            priority_values={},
            forecast_consensus={},
            advanced_metrics={},
            dividend_coverage={},
        )
        db.add(record)
    record.forecast_consensus = forecast_consensus
    priority = dict(record.priority_values or {})
    priority["forecast_consensus"] = forecast_consensus
    record.priority_values = priority
    flag_modified(record, "forecast_consensus")
    flag_modified(record, "priority_values")
    db.flush()
