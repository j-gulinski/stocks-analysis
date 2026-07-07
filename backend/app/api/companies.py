"""Company data endpoints: refresh (scrape), read views, dossier and forecasts."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_user_email
from app.api.schemas import (
    CompanyOut,
    DividendOut,
    DossierOut,
    FinancialsOut,
    ForecastAssumptionsIn,
    ForecastCreateIn,
    ForecastOut,
    IndicatorPointOut,
    PriceOut,
    RefreshSummaryOut,
    ReportRowOut,
)
from app.db.base import get_db
from app.db.models import Company, Dividend, Forecast, IndicatorValue, Price, ReportValue
from app.services import dossier as dossier_service
from app.services import forecast as forecast_service
from app.services import refresh as refresh_service

router = APIRouter(prefix="/companies", tags=["companies"])


def _get_company_or_404(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown company '{ticker.upper()}' — add it to the watchlist "
            "or refresh it first.",
        )
    return company


@router.post("/{ticker}/refresh", response_model=RefreshSummaryOut)
def refresh_company(
    ticker: str,
    scope: Literal["all", "financials", "prices"] = "all",
    force: bool = False,
    db: Session = Depends(get_db),
) -> RefreshSummaryOut:
    """Scrape BiznesRadar (+ stooq) for this ticker and upsert into the DB.

    Runs synchronously: a full refresh takes ~15–30 s because of the polite
    per-request delays. That is a feature, not a bug.
    """
    try:
        summary = refresh_service.refresh_company(db, ticker, scope=scope, force=force)
    except refresh_service.UnknownTickerError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return RefreshSummaryOut(ticker=ticker.upper(), summary=summary)


@router.get("/{ticker}/financials", response_model=FinancialsOut)
def get_financials(
    ticker: str,
    statement: Literal["income", "balance", "cashflow"] = "income",
    freq: Literal["Q", "Y"] = "Q",
    db: Session = Depends(get_db),
) -> FinancialsOut:
    """Stored statement reassembled into table form (periods × rows)."""
    company = _get_company_or_404(db, ticker)
    values = db.scalars(
        select(ReportValue).where(
            ReportValue.company_id == company.id,
            ReportValue.statement == statement,
            ReportValue.freq == freq,
        )
    ).all()

    periods = sorted({v.period for v in values})
    by_field: dict[str, dict] = {}
    for v in values:
        entry = by_field.setdefault(
            v.field_code,
            {"label": v.field_label, "position": v.position or 0, "values": {}},
        )
        entry["values"][v.period] = float(v.value) if v.value is not None else None

    rows = [
        ReportRowOut(
            field_code=code,
            label=entry["label"],
            values=[entry["values"].get(p) for p in periods],
        )
        for code, entry in sorted(by_field.items(), key=lambda kv: kv[1]["position"])
    ]
    return FinancialsOut(statement=statement, freq=freq, periods=periods, rows=rows)


@router.get("/{ticker}/indicators", response_model=dict[str, list[IndicatorPointOut]])
def get_indicators(
    ticker: str, db: Session = Depends(get_db)
) -> dict[str, list[IndicatorPointOut]]:
    company = _get_company_or_404(db, ticker)
    values = db.scalars(
        select(IndicatorValue)
        .where(IndicatorValue.company_id == company.id)
        .order_by(IndicatorValue.indicator, IndicatorValue.period)
    ).all()
    series: dict[str, list[IndicatorPointOut]] = {}
    for v in values:
        series.setdefault(v.indicator, []).append(
            IndicatorPointOut(
                period=v.period, value=float(v.value) if v.value is not None else None
            )
        )
    return series


@router.get("/{ticker}/dividends", response_model=list[DividendOut])
def get_dividends(ticker: str, db: Session = Depends(get_db)) -> list[Dividend]:
    company = _get_company_or_404(db, ticker)
    return db.scalars(
        select(Dividend)
        .where(Dividend.company_id == company.id)
        .order_by(Dividend.year.desc())
    ).all()


@router.get("/{ticker}/prices", response_model=list[PriceOut])
def get_prices(
    ticker: str,
    days: int = Query(default=365, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[Price]:
    company = _get_company_or_404(db, ticker)
    rows = db.scalars(
        select(Price)
        .where(Price.company_id == company.id)
        .order_by(Price.date.desc())
        .limit(days)
    ).all()
    return list(reversed(rows))  # chronological for charting


@router.get("/{ticker}/info", response_model=CompanyOut)
def get_company_info(ticker: str, db: Session = Depends(get_db)) -> Company:
    return _get_company_or_404(db, ticker)


# ------------------------------------------------------------ Phase 3: dossier

@router.get("/{ticker}", response_model=DossierOut)
def get_dossier(ticker: str, db: Session = Depends(get_db)) -> dict:
    """Everything about one company in a single response — the data contract
    shared by the stock page (frontend) and the AI analysis (Phase 5)."""
    company = _get_company_or_404(db, ticker)
    return dossier_service.build_dossier(db, company)


# ---------------------------------------------------------- Phase 3: forecasts

@router.get("/{ticker}/forecast-defaults", response_model=ForecastAssumptionsIn)
def get_forecast_defaults(
    ticker: str, db: Session = Depends(get_db)
) -> ForecastAssumptionsIn:
    """Assumptions prefilled from history, exactly like the Excel workflow."""
    company = _get_company_or_404(db, ticker)
    income = dossier_service.load_income_series(db, company.id)
    try:
        defaults = forecast_service.default_assumptions(income)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return ForecastAssumptionsIn(**defaults.to_dict())


@router.post("/{ticker}/forecasts", response_model=ForecastOut)
def create_forecast(
    ticker: str,
    payload: ForecastCreateIn,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
) -> ForecastOut:
    """Compute a forecast scenario; persists it unless save=false (live preview)."""
    company = _get_company_or_404(db, ticker)
    income = dossier_service.load_income_series(db, company.id)
    price, _ = dossier_service.latest_price(db, company.id)

    assumptions = forecast_service.ForecastAssumptions(**payload.assumptions.model_dump())
    result = forecast_service.compute_forecast(
        assumptions, income, company.shares_outstanding, price
    )

    if not payload.save:
        return ForecastOut(
            id=None,
            label=payload.label,
            assumptions=assumptions.to_dict(),
            result=result,
            created_at=None,
        )

    record = Forecast(
        company_id=company.id,
        label=payload.label,
        assumptions=assumptions.to_dict(),
        result=result,
        created_by=user_email,
    )
    db.add(record)
    db.commit()
    return ForecastOut(
        id=record.id,
        label=record.label,
        assumptions=record.assumptions,
        result=record.result,
        created_at=record.created_at,
    )


@router.get("/{ticker}/forecasts", response_model=list[ForecastOut])
def list_forecasts(ticker: str, db: Session = Depends(get_db)) -> list[ForecastOut]:
    company = _get_company_or_404(db, ticker)
    records = db.scalars(
        select(Forecast)
        .where(Forecast.company_id == company.id)
        .order_by(Forecast.created_at.desc(), Forecast.id.desc())
    ).all()
    return [
        ForecastOut(
            id=r.id,
            label=r.label,
            assumptions=r.assumptions,
            result=r.result,
            created_at=r.created_at,
        )
        for r in records
    ]
