"""Watchlist CRUD — the entry point of the whole workflow: add a ticker here,
then refresh, browse and analyze it."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.api.schemas import WatchlistAddIn, WatchlistItemOut
from app.db.base import get_db
from app.db.models import (
    Analysis,
    Company,
    Dividend,
    Forecast,
    ForumTopic,
    IndicatorValue,
    Price,
    ReportValue,
    ThesisFalsifier,
    WatchlistItem,
)
from app.services.refresh import get_or_create_company

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _risk_summary(db: Session, company_id: int) -> tuple[str, int, int]:
    rows = db.scalars(
        select(ThesisFalsifier.status).where(ThesisFalsifier.company_id == company_id)
    ).all()
    fired = sum(status == "fired" for status in rows)
    warning = sum(status == "warning" for status in rows)
    level = "fired" if fired else "warning" if warning else "none"
    return level, fired, warning


@router.get("", response_model=list[WatchlistItemOut])
def list_watchlist(db: Session = Depends(get_db)) -> list[WatchlistItemOut]:
    rows = db.execute(
        select(WatchlistItem, Company)
        .join(Company, WatchlistItem.company_id == Company.id)
        .order_by(WatchlistItem.added_at)
    ).all()
    result = []
    for item, company in rows:
        risk_level, fired, warning = _risk_summary(db, company.id)
        result.append(
            WatchlistItemOut(
                ticker=company.ticker,
                name=company.name,
                note=item.note,
                added_at=item.added_at,
                risk_level=risk_level,
                fired_falsifiers=fired,
                warning_falsifiers=warning,
            )
        )
    risk_order = {"fired": 0, "warning": 1, "none": 2}
    return sorted(result, key=lambda row: (risk_order.get(row.risk_level, 3), row.added_at))


@router.post("", response_model=WatchlistItemOut, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(
    payload: WatchlistAddIn, db: Session = Depends(get_db)
) -> WatchlistItemOut:
    company = get_or_create_company(db, payload.ticker)
    exists = db.scalar(
        select(WatchlistItem).where(WatchlistItem.company_id == company.id)
    )
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{company.ticker} is already on the watchlist.",
        )
    item = WatchlistItem(company_id=company.id, note=payload.note)
    db.add(item)
    db.commit()
    risk_level, fired, warning = _risk_summary(db, company.id)
    return WatchlistItemOut(
        ticker=company.ticker,
        name=company.name,
        note=item.note,
        added_at=item.added_at,
        risk_level=risk_level,
        fired_falsifiers=fired,
        warning_falsifiers=warning,
    )


@router.delete("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db)) -> None:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{ticker.upper()} is not on the watchlist.",
        )
    item = db.scalar(select(WatchlistItem).where(WatchlistItem.company_id == company.id))
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{ticker.upper()} is not on the watchlist.",
        )

    # Product semantics: removing a ticker means "forget this analysis", not
    # merely hiding it from the dashboard. Keep forum topics/posts as source
    # archive, but detach them from the company; purge company-owned analytics.
    company_id = company.id
    db.execute(delete(Analysis).where(Analysis.company_id == company_id))
    db.execute(delete(Forecast).where(Forecast.company_id == company_id))
    db.execute(delete(Price).where(Price.company_id == company_id))
    db.execute(delete(Dividend).where(Dividend.company_id == company_id))
    db.execute(delete(IndicatorValue).where(IndicatorValue.company_id == company_id))
    db.execute(delete(ReportValue).where(ReportValue.company_id == company_id))
    db.execute(update(ForumTopic).where(ForumTopic.company_id == company_id).values(company_id=None))
    db.delete(item)
    db.delete(company)
    db.commit()
