"""Diagnostics endpoints — the 'why is there no data?' toolbox.

Born from a production session where refresh looked successful but the income
statement mapped zero fields and prices silently failed. These endpoints make
every integration's state visible instead of leaving dashes in the UI.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Company, FetchLog, IndicatorValue, ReportValue
from app.services import fields
from app.services import refresh as refresh_service

router = APIRouter(tags=["diagnostics"])

SOURCES = {
    "biznesradar.pl": "%biznesradar.pl%",
    "portalanaliz.pl": "%portalanaliz.pl%",
}


@router.get("/health/scrapers")
def scrapers_health(db: Session = Depends(get_db)) -> dict:
    """Per-source status from fetch_log: last success, last failure, 24 h errors."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    result: dict[str, dict] = {}
    for name, pattern in SOURCES.items():
        last_ok = db.execute(
            select(FetchLog.url, FetchLog.fetched_at)
            .where(FetchLog.url.like(pattern), FetchLog.status == 200)
            .order_by(FetchLog.fetched_at.desc())
            .limit(1)
        ).first()
        last_fail = db.execute(
            select(FetchLog.url, FetchLog.status, FetchLog.fetched_at)
            .where(
                FetchLog.url.like(pattern),
                (FetchLog.status.is_(None)) | (FetchLog.status != 200),
            )
            .order_by(FetchLog.fetched_at.desc())
            .limit(1)
        ).first()
        errors_24h = db.scalar(
            select(func.count())
            .select_from(FetchLog)
            .where(
                FetchLog.url.like(pattern),
                FetchLog.fetched_at >= since,
                (FetchLog.status.is_(None)) | (FetchLog.status != 200),
            )
        )
        result[name] = {
            "last_ok_at": last_ok.fetched_at if last_ok else None,
            "last_error": (
                {
                    "url": last_fail.url,
                    "status": last_fail.status,
                    "at": last_fail.fetched_at,
                }
                if last_fail
                else None
            ),
            "errors_24h": int(errors_24h or 0),
        }
    return result


@router.get("/diagnostics/br-login-status")
def br_login_status() -> dict:
    """P1.9: verifies BR_USERNAME/BR_PASSWORD actually log in.

    Mirrors /forum/login-status (app/api/forum.py). Deliberately NOT placed
    at /companies/br-login-status: that single path segment would be caught
    by companies.router's `GET /companies/{ticker}` dossier route (routers
    are matched in registration order in app/main.py, and companies.router
    is registered before diagnostics.router) — this path avoids the clash.

    ASSUMPTION CAVEAT: BiznesRadar's real login markup is unverified in this
    codebase (see app/scrapers/biznesradar.py BrClient docstring). A `false`
    result on believed-correct credentials may mean the parser needs fixing
    against a real recorded login page, not that the credentials are wrong.
    """
    return refresh_service.check_br_login()


@router.get("/companies/{ticker}/mapping-report")
def mapping_report(ticker: str, db: Session = Depends(get_db)) -> dict:
    """Every stored statement row + whether services/fields.py understands it.

    When metrics show 'b/d' after a successful refresh, this is the first
    thing to check: unmapped labels mean the alias lists need extending —
    no re-scrape required, the raw rows are already in the DB.
    """
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown company '{ticker}'."
        )

    rows = db.execute(
        select(
            ReportValue.statement,
            ReportValue.field_code,
            ReportValue.field_label,
            func.count().label("values"),
        )
        .where(ReportValue.company_id == company.id)
        .group_by(ReportValue.statement, ReportValue.field_code, ReportValue.field_label)
        .order_by(ReportValue.statement, func.min(ReportValue.position))
    ).all()

    report: dict[str, list[dict]] = {"income": [], "balance": [], "cashflow": []}
    unmapped = 0
    for row in rows:
        if row.statement == "income":
            canonical = fields.match_income_field(row.field_label, row.field_code)
        elif row.statement == "balance":
            canonical = fields.match_balance_field(row.field_label, row.field_code)
        else:
            canonical = None  # cashflow rows are stored raw by design in v1
        if canonical is None and row.statement != "cashflow":
            unmapped += 1
        report.setdefault(row.statement, []).append(
            {
                "field_code": row.field_code,
                "label": row.field_label,
                "canonical": canonical,
                "stored_values": row.values,
            }
        )

    indicators = list(
        db.scalars(
            select(IndicatorValue.indicator)
            .where(IndicatorValue.company_id == company.id)
            .distinct()
        )
    )
    # Indicator rows are NOT stored raw, so a dropped label is invisible here
    # post-hoc — the refresh summary lists "pominięte: …" live instead. This
    # section shows which known codes never produced data for this company.
    known_codes = sorted(set(fields.INDICATOR_CODES.values()))
    indicators_missing = [code for code in known_codes if code not in indicators]

    return {
        "ticker": company.ticker,
        "unmapped_statement_rows": unmapped,
        "statements": report,
        "indicators_stored": indicators,
        "indicators_never_seen": indicators_missing,
        "hint": (
            "Rows with canonical=null are invisible to metrics. Paste this JSON "
            "into a session and the aliases in services/fields.py get extended. "
            "Unrecognized indicator labels appear in the refresh summary as "
            "'pominięte: …'."
        ),
    }
