"""Watchlist CRUD — the entry point of the whole workflow: add a ticker here,
then refresh, browse and analyze it."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import WatchlistAddIn, WatchlistItemOut
from app.db.base import get_db
from app.db.models import Company, WatchlistItem
from app.services.refresh import get_or_create_company

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemOut])
def list_watchlist(db: Session = Depends(get_db)) -> list[WatchlistItemOut]:
    rows = db.execute(
        select(WatchlistItem, Company)
        .join(Company, WatchlistItem.company_id == Company.id)
        .order_by(WatchlistItem.added_at)
    ).all()
    return [
        WatchlistItemOut(
            ticker=company.ticker, name=company.name, note=item.note, added_at=item.added_at
        )
        for item, company in rows
    ]


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
    return WatchlistItemOut(
        ticker=company.ticker, name=company.name, note=item.note, added_at=item.added_at
    )


@router.delete("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db)) -> None:
    item = db.scalar(
        select(WatchlistItem)
        .join(Company, WatchlistItem.company_id == Company.id)
        .where(Company.ticker == ticker.upper())
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{ticker.upper()} is not on the watchlist.",
        )
    db.delete(item)
    db.commit()
