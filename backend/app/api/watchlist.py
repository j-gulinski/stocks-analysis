"""Optional watchlist membership over durable Research Lab company data."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import WatchlistAddIn, WatchlistItemOut
from app.db.base import get_db
from app.db.models import Company, ThesisFalsifier, WatchlistItem
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

    # Watchlist is only a membership view. Research identity, immutable
    # evidence and analysis history belong to the Research Lab and survive.
    db.delete(item)
    db.commit()
