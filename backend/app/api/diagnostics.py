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
from app.db.models import AgentRun, AnalysisRun, Company, FetchLog, IndicatorValue, ReportValue
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

    The login recipe is verified live (POST /login/ + 'account-settings'
    marker — see app/scrapers/biznesradar.py BrClient), so a `false` result on
    believed-correct credentials points at the credentials themselves
    (BR_USERNAME is the account e-mail) or a site change.
    """
    return refresh_service.check_br_login()


@router.get("/diagnostics/workflow-status")
def workflow_status(db: Session = Depends(get_db)) -> dict:
    """Codex workflow status for Settings.

    CX.9 retires the old provider-key check from the UI. The useful local
    health question is now whether Codex-facing durable queues and verified
    analysis rows are visible to the app.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    queued = db.scalar(
        select(func.count()).select_from(AgentRun).where(AgentRun.status == "queued")
    )
    running = db.scalar(
        select(func.count()).select_from(AgentRun).where(AgentRun.status == "running")
    )
    completed_24h = db.scalar(
        select(func.count())
        .select_from(AgentRun)
        .where(
            AgentRun.status.in_(("completed", "verified")),
            AgentRun.updated_at >= since,
        )
    )
    verified_24h = db.scalar(
        select(func.count())
        .select_from(AnalysisRun)
        .where(
            AnalysisRun.verification_status == "pass",
            AnalysisRun.created_at >= since,
        )
    )
    latest = db.scalar(select(func.max(AgentRun.updated_at)).select_from(AgentRun))
    return {
        "ok": True,
        "queued": int(queued or 0),
        "running": int(running or 0),
        "completed_24h": int(completed_24h or 0),
        "verified_24h": int(verified_24h or 0),
        "latest_run_at": latest,
    }


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
