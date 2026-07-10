"""Read-only position context plus explicit CSV import."""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import MyfundImportIn, PositionCsvImportIn, PositionImportOut, PositionOut
from app.config import get_settings
from app.db.base import get_db
from app.db.models import Company, PositionLedgerEntry, utcnow
from app.scrapers import http as polite_http

router = APIRouter(prefix="/positions", tags=["positions"])


def _decimal(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value.strip().replace(" ", "").replace(",", "."))


def _date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    return date.fromisoformat(value.strip())


def _out(row: PositionLedgerEntry) -> PositionOut:
    return PositionOut(
        id=row.id,
        ticker=row.ticker,
        instrument_name=row.instrument_name,
        portfolio=row.portfolio,
        entry_date=row.entry_date,
        entry_price=float(row.entry_price) if row.entry_price is not None else None,
        quantity=float(row.quantity) if row.quantity is not None else None,
        size_pln=float(row.size_pln) if row.size_pln is not None else None,
        sizing_rule_flag=row.sizing_rule_flag,
        source=row.source,
        imported_at=row.imported_at,
    )


def _existing_position(
    db: Session, *, source: str, portfolio: str, source_ref: str
) -> PositionLedgerEntry | None:
    return db.scalar(
        select(PositionLedgerEntry).where(
            PositionLedgerEntry.source == source,
            PositionLedgerEntry.portfolio == portfolio,
            PositionLedgerEntry.source_ref == source_ref,
        )
    )


def _myfund_tickers(payload: Any) -> list[dict[str, Any]]:
    tickers = payload.get("tickers") if isinstance(payload, dict) else None
    if isinstance(tickers, dict):
        return [row for row in tickers.values() if isinstance(row, dict)]
    if isinstance(tickers, list):
        return [row for row in tickers if isinstance(row, dict)]
    return []


@router.get("", response_model=list[PositionOut])
def list_positions(
    ticker: str | None = Query(default=None, max_length=12),
    portfolio: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
) -> list[PositionOut]:
    stmt = select(PositionLedgerEntry).order_by(
        PositionLedgerEntry.ticker.asc(), PositionLedgerEntry.entry_date.asc()
    )
    if ticker:
        stmt = stmt.where(PositionLedgerEntry.ticker == ticker.upper())
    if portfolio:
        stmt = stmt.where(PositionLedgerEntry.portfolio == portfolio)
    return [_out(row) for row in db.scalars(stmt).all()]


@router.post("/import/csv", response_model=PositionImportOut)
def import_positions_csv(
    payload: PositionCsvImportIn,
    db: Session = Depends(get_db),
) -> PositionImportOut:
    """Import a user-exported CSV; unmatched instruments are returned, not guessed."""
    reader = csv.DictReader(io.StringIO(payload.csv_text))
    required = {"ticker", "instrument", "entry_date", "entry_price", "quantity", "size_pln", "sizing_rule_flag"}
    headers = {header.strip() for header in (reader.fieldnames or [])}
    missing = sorted(required - headers)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"CSV missing columns: {', '.join(missing)}",
        )

    imported: list[PositionLedgerEntry] = []
    unmatched: list[str] = []
    skipped_duplicates = 0
    for index, raw in enumerate(reader, start=2):
        ticker = (raw.get("ticker") or "").strip().upper()
        instrument = (raw.get("instrument") or "").strip() or ticker or f"row {index}"
        if not ticker:
            unmatched.append(f"{instrument} (row {index}: missing ticker mapping)")
            continue
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        if company is None:
            unmatched.append(f"{instrument} (row {index}: unknown ticker {ticker})")
            continue
        source_ref = (raw.get("source_ref") or "").strip() or f"row-{index}-{ticker}"
        duplicate = _existing_position(
            db,
            source="csv",
            portfolio=payload.portfolio,
            source_ref=source_ref,
        )
        if duplicate is not None:
            skipped_duplicates += 1
            continue
        try:
            row = PositionLedgerEntry(
                company_id=company.id,
                ticker=ticker,
                instrument_name=instrument,
                portfolio=payload.portfolio.strip(),
                entry_date=_date(raw.get("entry_date")),
                entry_price=_decimal(raw.get("entry_price")),
                quantity=_decimal(raw.get("quantity")),
                size_pln=_decimal(raw.get("size_pln")),
                sizing_rule_flag=(raw.get("sizing_rule_flag") or "").strip().lower() in {"1", "true", "yes", "tak"},
                source="csv",
                source_ref=source_ref,
                imported_at=utcnow(),
            )
        except (TypeError, ValueError) as exc:
            unmatched.append(f"{instrument} (row {index}: invalid value: {exc})")
            continue
        db.add(row)
        imported.append(row)
    db.commit()
    for row in imported:
        db.refresh(row)
    return PositionImportOut(
        imported=len(imported),
        skipped_duplicates=skipped_duplicates,
        unmatched=unmatched,
        positions=[_out(row) for row in imported],
    )


@router.post("/import/myfund", response_model=PositionImportOut)
def import_positions_myfund(
    payload: MyfundImportIn,
    db: Session = Depends(get_db),
) -> PositionImportOut:
    """Pull one configured myfund portfolio during an explicit user session."""
    settings = get_settings()
    portfolio = (payload.portfolio or settings.myfund_portfolio or "").strip()
    if not settings.myfund_api_key or not portfolio:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="myfund API key and one pinned portfolio are required.",
        )
    url = settings.myfund_base_url.rstrip("/") + "/API/v1/getPortfel.php"
    try:
        response = polite_http.fetch(
            url,
            params={
                "portfel": portfolio,
                "apiKey": settings.myfund_api_key,
                "format": "json",
            },
        )
        payload_json = response.json()
    except Exception as exc:
        # Never include the URL/query in the error: it contains the API key.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"myfund import failed: {type(exc).__name__}",
        ) from exc

    status_payload = payload_json.get("status") if isinstance(payload_json, dict) else None
    if isinstance(status_payload, dict) and str(status_payload.get("code")) not in {"0", "None"}:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="myfund returned an error status.",
        )

    imported: list[PositionLedgerEntry] = []
    unmatched: list[str] = []
    skipped_duplicates = 0
    for index, raw in enumerate(_myfund_tickers(payload_json), start=1):
        ticker = str(raw.get("tickerClear") or "").strip().upper()
        instrument = str(raw.get("nazwa") or ticker or f"myfund row {index}").strip()
        if not ticker:
            unmatched.append(f"{instrument} (missing ticker mapping)")
            continue
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        if company is None:
            unmatched.append(f"{instrument} (unknown ticker {ticker})")
            continue
        source_ref = ticker
        if _existing_position(
            db, source="myfund", portfolio=portfolio, source_ref=source_ref
        ) is not None:
            skipped_duplicates += 1
            continue
        try:
            row = PositionLedgerEntry(
                company_id=company.id,
                ticker=ticker,
                instrument_name=instrument,
                portfolio=portfolio,
                entry_date=None,
                entry_price=_decimal(str(raw.get("cenaZakupu") or "")),
                quantity=_decimal(str(raw.get("liczbaJednostek") or "")),
                size_pln=_decimal(str(raw.get("wartosc") or "")),
                sizing_rule_flag=False,
                source="myfund",
                source_ref=source_ref,
                imported_at=utcnow(),
            )
        except (TypeError, ValueError) as exc:
            unmatched.append(f"{instrument} (invalid value: {exc})")
            continue
        db.add(row)
        imported.append(row)
    db.commit()
    for row in imported:
        db.refresh(row)
    return PositionImportOut(
        imported=len(imported),
        skipped_duplicates=skipped_duplicates,
        unmatched=unmatched,
        positions=[_out(row) for row in imported],
    )
