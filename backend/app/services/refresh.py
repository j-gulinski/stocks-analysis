"""Refresh orchestration: scrape BiznesRadar for one company → upsert DB.

Responsibilities split (see PLAN §2): scrapers fetch and parse, THIS service
owns persistence, caching and error isolation. One failed page never fails a
whole refresh — the summary tells the UI exactly what happened per page.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Statement rows that are metadata, not financial values (e.g. publication
# dates would be parsed as the number 2025) — never stored.
IGNORED_ROW_LABELS = ("data publikacji",)

from app.config import get_settings
from app.db.models import (
    Company,
    Dividend,
    FetchLog,
    DocumentVersion,
    IndicatorValue,
    Price,
    ReportValue,
    SourceDocument,
    utcnow,
)
from app.scrapers import biznesradar
from app.scrapers import http as polite_http
from app.services import evidence, fields, market_data, publication_dates, report_calendar

# report pages: kind -> (statement, freq)
REPORT_PAGES = publication_dates.STATEMENT_REPORT_SCOPES
INDICATOR_PAGES = ("indicators_value", "indicators_profitability")
# Below this many stored price rows the app has no real history and a
# successful provider fetch REPLACES what is there (backfill).
MIN_PRICE_HISTORY_ROWS = 30
PROFILE_SCALAR_EXTRACTOR_VERSION = "biznesradar-profile-scalars@1"


class UnknownTickerError(Exception):
    """Ticker not found on BiznesRadar and unknown locally."""


@dataclass(frozen=True)
class FetchedPage:
    text: str
    content: bytes
    requested_url: str
    effective_url: str
    status_code: int
    mime_type: str
    fetched_at: datetime
    fetch_log: FetchLog


@dataclass(frozen=True)
class ProfileRefreshResult:
    price: float | None = None
    source_version_id: int | None = None
    report_schedule_id: int | None = None


@dataclass(frozen=True)
class RecordedPriceHistory:
    bars: list[biznesradar.PriceBar]
    source_version_id: int
    fetched_at: datetime


# --------------------------------------------------------- premium session


def _build_br_session(summary: dict[str, str]) -> requests.Session | None:
    """P1.9: optional logged-in BiznesRadar session, threaded into every BR
    fetch below. Premium is an ENHANCEMENT, never a hard dependency — a login
    failure is recorded in the summary and the refresh continues anonymously
    (identical to pre-P1.9 behaviour) rather than aborting.

    The login recipe (POST /login/ with {email, password}, confirmed by the
    'account-settings' homepage marker) is verified live — see
    app/scrapers/biznesradar.py BrClient. A recorded "error" here therefore
    points at the credentials (BR_USERNAME is the account e-mail / BR_PASSWORD)
    or a site change, not at unverified plumbing.
    """
    settings = get_settings()
    if not (settings.br_username and settings.br_password):
        summary["br_login"] = "pominięto (brak danych logowania)"
        return None
    try:
        client = biznesradar.BrClient()
        client.login(settings.br_username, settings.br_password)
    except (
        biznesradar.BrLoginError,
        polite_http.FetchError,
        requests.RequestException,
    ) as exc:
        logger.warning("BiznesRadar premium login failed: %s", exc)
        summary["br_login"] = f"error: {exc}"
        return None
    # Refresh summaries are returned to the browser. Authentication state is
    # useful; the account identifier is not and must never leave server config.
    summary["br_login"] = "ok (zalogowano)"
    return client.session


def check_br_login() -> dict:
    """Diagnostics endpoint: verifies BR_USERNAME/BR_PASSWORD actually work.

    Must NEVER raise. Performs a real login round-trip (POST /login/ plus the
    account-settings marker check) using the verified BrClient recipe.
    """
    settings = get_settings()
    if not (settings.br_username and settings.br_password):
        return {
            "ok": False,
            "status": "not_configured",
            "detail": "BR_USERNAME / BR_PASSWORD not configured.",
        }
    try:
        client = biznesradar.BrClient()
        client.login(settings.br_username, settings.br_password)
        return {
            "ok": True,
            "status": "ok",
            "detail": "BiznesRadar login verified.",
        }
    except Exception as exc:  # noqa: BLE001 — diagnostics endpoint, see docstring
        return {
            "ok": False,
            "status": "error",
            "detail": f"{type(exc).__name__}: {exc}",
        }


def get_or_create_company(db: Session, ticker: str) -> Company:
    ticker = ticker.strip().upper()
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if company is None:
        company = Company(ticker=ticker)
        db.add(company)
        db.flush()  # assign id without committing the transaction yet
    return company


# ------------------------------------------------------------ fetch helpers

def _log_fetch(db: Session, url: str, status: int | None) -> FetchLog:
    row = FetchLog(url=url, status=status, fetched_at=utcnow())
    db.add(row)
    return row


def _is_fresh(db: Session, url: str) -> bool:
    """True when the URL was fetched successfully within the cache window."""
    ttl_hours = get_settings().scrape_cache_hours
    threshold = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    last_ok = db.scalar(
        select(FetchLog.fetched_at)
        .where(FetchLog.url == url, FetchLog.status == 200)
        .order_by(FetchLog.fetched_at.desc())
        .limit(1)
    )
    if last_ok is None:
        return False
    if last_ok.tzinfo is None:  # SQLite drops tzinfo; stored values are UTC
        last_ok = last_ok.replace(tzinfo=timezone.utc)
    return last_ok >= threshold


def _get_page(
    db: Session,
    url: str,
    force: bool,
    session: requests.Session | None = None,
) -> FetchedPage | None:
    """Fetch a page through the polite client; None means 'use cache / skip'.

    `session` reuses cookies (P1.9: an optional logged-in BiznesRadar premium
    session) — None (the default) fetches exactly as before this task.
    """
    if not force and _is_fresh(db, url):
        return None
    try:
        response = polite_http.fetch(url, session=session)
    except (requests.RequestException, polite_http.FetchError):
        # Source attempts are durable even when no response exists, so stored
        # views can distinguish stale evidence from a failed refresh.
        _log_fetch(db, url, None)
        db.commit()
        raise
    fetch_log = _log_fetch(db, url, response.status_code)
    if response.status_code == 404:
        db.commit()
        raise LookupError(f"404 for {url}")
    try:
        response.raise_for_status()  # non-retryable, non-404 errors are real errors
    except requests.RequestException:
        db.commit()
        raise
    content = getattr(response, "content", None) or response.text.encode("utf-8")
    headers = getattr(response, "headers", {}) or {}
    mime_type = headers.get("content-type", "text/html").split(";", 1)[0].strip()
    return FetchedPage(
        text=response.text,
        content=content,
        requested_url=url,
        effective_url=str(getattr(response, "url", None) or url),
        status_code=response.status_code,
        mime_type=mime_type,
        fetched_at=fetch_log.fetched_at,
        fetch_log=fetch_log,
    )


def _merge_premium_nodes(db: Session, company: Company, html: str) -> None:
    parsed = biznesradar.parse_premium_market_data(html).to_dict()
    if any(parsed.get(key) for key in ("forecast_consensus", "advanced_metrics", "dividend_coverage")):
        market_data.merge_premium_market_data(db, company, parsed)


# ------------------------------------------------------------------ upserts

def _upsert_report_values(
    db: Session,
    company: Company,
    statement: str,
    table: biznesradar.ReportTable,
    source_version: DocumentVersion,
    replace: bool = False,
) -> int:
    """Store report cells; returns number of processed values.

    Two production crashes taught this function humility, so it is now
    collision-proof by construction:
    - `replace=True` (forced refresh) first DELETES the statement's stored
      rows — a re-scrape is authoritative and must purge stale/mislabeled
      periods from earlier runs, which plain upserts never could.
    - Writing uses the database's native INSERT … ON CONFLICT DO UPDATE
      (PostgreSQL and SQLite alike), after in-memory dedup — a duplicate
      (period, field) can no longer raise UniqueViolation, whatever the
      page served.
    """
    if replace:
        db.execute(
            delete(ReportValue).where(
                ReportValue.company_id == company.id,
                ReportValue.statement == statement,
                ReportValue.freq == table.freq,
            )
        )

    now = utcnow()
    rows_by_key: dict[tuple[str, str], dict] = {}
    for position, row in enumerate(table.rows):
        if row.label.strip().lower() in IGNORED_ROW_LABELS:
            continue
        for period, value in zip(table.periods, row.values):
            # last occurrence wins within one page — keys must be unique
            # inside a single ON CONFLICT statement
            rows_by_key[(period, row.field_code)] = {
                "company_id": company.id,
                "statement": statement,
                "freq": table.freq,
                "period": period,
                "field_code": row.field_code,
                "field_label": row.label,
                "position": position,
                "value": value,
                "scraped_at": now,
                "_locator": {
                    "table": statement,
                    "frequency": table.freq,
                    "row_position": position,
                    "field_code": row.field_code,
                    "field_label": row.label,
                    "period": period,
                },
            }

    publication_dates.record_statement_publication_facts(
        db,
        company,
        statement,
        table,
        source_version,
    )

    if not rows_by_key:
        return 0

    for payload in rows_by_key.values():
        locator = payload.pop("_locator")
        fact = evidence.record_numeric_fact(
            db,
            company,
            source_version,
            fact_type="financial_statement",
            fact_key=f"{statement}.{payload['field_code']}",
            value=payload["value"],
            unit="tys_pln",
            period=payload["period"],
            locator=locator,
        )
        payload["source_fact_id"] = fact.id

    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

    statement_insert = dialect_insert(ReportValue).values(list(rows_by_key.values()))
    statement_insert = statement_insert.on_conflict_do_update(
        index_elements=["company_id", "statement", "freq", "period", "field_code"],
        set_={
            "value": statement_insert.excluded.value,
            "field_label": statement_insert.excluded.field_label,
            "position": statement_insert.excluded.position,
            "scraped_at": statement_insert.excluded.scraped_at,
            "source_fact_id": statement_insert.excluded.source_fact_id,
        },
    )
    db.execute(statement_insert)
    return len(rows_by_key)


def _upsert_indicators(
    db: Session,
    company: Company,
    table: biznesradar.ReportTable,
    source_version: DocumentVersion,
) -> tuple[int, list[str]]:
    """Returns (stored value count, labels the mapper did not recognize).

    Unmapped labels are surfaced in the refresh summary — a silently dropped
    indicator ("why is C/ZO missing?") used to be invisible to diagnostics
    because raw indicator rows are not stored.
    """
    existing: dict[tuple[str, str], IndicatorValue] = {
        (iv.indicator, iv.period): iv
        for iv in db.scalars(
            select(IndicatorValue).where(IndicatorValue.company_id == company.id)
        )
    }
    now = utcnow()
    count = 0
    unmapped: list[str] = []
    for row_position, row in enumerate(table.rows):
        # Code-first (data-field survives label drift), label as fallback.
        code = fields.match_indicator(row.label, row.field_code)
        if code is None:
            unmapped.append(row.label)
            continue
        for period, value in zip(table.periods, row.values):
            fact = evidence.record_numeric_fact(
                db,
                company,
                source_version,
                fact_type="indicator",
                fact_key=f"indicator.{code}",
                value=value,
                unit=fields.indicator_unit(code),
                period=period,
                locator={
                    "table": "indicator",
                    "row_position": row_position,
                    "source_field_code": row.field_code,
                    "source_label": row.label,
                    "canonical_indicator": code,
                    "period": period,
                },
            )
            record = existing.get((code, period))
            if record is None:
                record = IndicatorValue(
                    company_id=company.id, indicator=code, period=period, value=value
                )
                db.add(record)
                existing[(code, period)] = record
            else:
                evidence.record_conflict_if_needed(
                    db,
                    company,
                    previous_fact_id=record.source_fact_id,
                    new_fact=fact,
                )
                record.value = value
            record.source_fact_id = fact.id
            record.scraped_at = now
            count += 1
    return count, unmapped


def _upsert_dividends(
    db: Session, company: Company, entries: list[biznesradar.DividendEntry]
) -> int:
    existing = {
        d.year: d
        for d in db.scalars(select(Dividend).where(Dividend.company_id == company.id))
    }
    for entry in entries:
        record = existing.get(entry.year)
        if record is None:
            db.add(
                Dividend(
                    company_id=company.id,
                    year=entry.year,
                    dps=entry.dps,
                    yield_pct=entry.yield_pct,
                )
            )
        else:
            record.dps = entry.dps
            record.yield_pct = entry.yield_pct
    return len(entries)


# ----------------------------------------------------------------- refresh

def refresh_company(
    db: Session, ticker: str, scope: str = "all", force: bool = False
) -> dict[str, str]:
    """Refresh one company; returns page-by-page status summary.

    Resilience rule: ONE wrong/missing page never blanks the refresh — every
    page degrades independently to an `error: …` entry. UnknownTickerError is
    raised only when literally nothing succeeded and the company has no data,
    i.e. the ticker really does not exist on BiznesRadar.
    """
    company = get_or_create_company(db, ticker)
    summary: dict[str, str] = {}
    requests_before = db.scalar(select(func.count()).select_from(FetchLog)) or 0
    profile_price: float | None = None
    profile_source_version_id: int | None = None
    report_schedule_id: int | None = None

    # P1.9: optional premium session, built once and reused for every BR page
    # this refresh touches. No BR_USERNAME/BR_PASSWORD configured -> session
    # stays None and every fetch below behaves exactly as before this task.
    br_session = _build_br_session(summary)

    if scope in ("financials", "all"):
        profile_result = _refresh_profile(
            db, company, force, summary, session=br_session
        )
        profile_price = profile_result.price
        profile_source_version_id = profile_result.source_version_id
        report_schedule_id = profile_result.report_schedule_id
        _refresh_reports(db, company, force, summary, session=br_session)
        _refresh_indicators(db, company, force, summary, session=br_session)
        _refresh_dividends(db, company, force, summary, session=br_session)

        every_page_failed = all(
            status.startswith(("error", "none"))
            for key, status in summary.items()
            if key not in ("br_login", "forecasts")
        )
        if every_page_failed and company.name is None and not _has_any_data(db, company):
            db.commit()  # keep fetch_log entries for debugging
            raise UnknownTickerError(
                f"Ticker '{company.ticker}' not found on BiznesRadar "
                f"(all pages failed: {summary})."
            )
        _refresh_forecasts(db, company, force, summary, session=br_session)
        market_data.upsert_company_market_data(db, company)
        summary["company_market_data"] = "ok (priority AI context refreshed)"

    if scope in ("prices", "all"):
        if scope == "prices":
            profile_result = _refresh_profile(
                db, company, force, summary, session=br_session
            )
            profile_price = profile_result.price
            profile_source_version_id = profile_result.source_version_id
            report_schedule_id = profile_result.report_schedule_id
        summary["prices"] = _refresh_prices(
            db,
            company,
            fallback_price=profile_price,
            fallback_source_version_id=profile_source_version_id,
            session=br_session,
        )

    # Freeze the calendar producer only after every page in this bounded
    # refresh has been recorded. Its Research idempotency fingerprint must see
    # the same final evidence state that an immediate manual review sees.
    if report_schedule_id is not None:
        schedule = report_calendar.reconcile_schedule(
            db, schedule_id=report_schedule_id, company_id=company.id
        )
        _summarize_report_calendar(schedule=schedule, summary=summary)

    company.updated_at = utcnow()
    try:
        db.commit()
    except IntegrityError as exc:
        # Never 500 a refresh over a storage conflict: report it like any
        # other per-source problem and keep the API contract intact.
        db.rollback()
        logger.error("refresh commit failed for %s: %s", company.ticker, exc.orig)
        summary["database"] = f"error: {exc.orig}"
        return summary

    # Forum synchronisation was deleted with the legacy dossier stack (VISION
    # V10). Retained forum posts stay readable as stored evidence; new forum
    # material enters only through explicit research-source collection.

    # Fetch-volume transparency: exactly how many HTTP requests this refresh
    # made (0 when everything came from the 24 h cache).
    requests_after = db.scalar(select(func.count()).select_from(FetchLog)) or 0
    summary["requests"] = f"ok ({requests_after - requests_before} HTTP)"
    return summary


def _has_any_data(db: Session, company: Company) -> bool:
    return (
        db.scalar(
            select(ReportValue.id).where(ReportValue.company_id == company.id).limit(1)
        )
        is not None
    )


def _report_slug(company: Company) -> str:
    """Slug for report URLs — ticker URLs redirect and LOSE the ,Q suffix."""
    return company.br_slug or company.ticker


def _record_page_evidence(
    db: Session,
    company: Company,
    page: FetchedPage,
    *,
    source_type: str,
    scope_key: str,
) -> evidence.RecordedDocument:
    recorded = evidence.record_document_version(
        db,
        company,
        source_name="biznesradar",
        source_type=source_type,
        scope_key=scope_key,
        requested_url=page.requested_url,
        effective_url=page.effective_url,
        content=page.content,
        text=page.text,
        response_status=page.status_code,
        mime_type=page.mime_type,
        fetched_at=page.fetched_at,
    )
    page.fetch_log.document_version_id = recorded.version.id
    return recorded


def _require_usable_grid(table: biznesradar.ReportTable) -> None:
    """Never let a structurally empty forced page erase current serving data."""
    if not table.periods or not table.rows:
        raise biznesradar.ParseError("parsed page has no usable period/value grid")
    if not any(any(value is not None for value in row.values) for row in table.rows):
        raise biznesradar.ParseError("parsed page has no numeric values")


def _refresh_profile(
    db: Session,
    company: Company,
    force: bool,
    summary: dict[str, str],
    session: requests.Session | None = None,
) -> ProfileRefreshResult:
    """Update company metadata; returns the current quote when the page shows
    one (used as the price source of last resort).

    Also resolves `br_slug` — without it every quarterly report URL would
    redirect to the annual view, so a missing slug overrides the page cache.
    """
    url = biznesradar.page_url("profile", company.ticker)
    must_fetch = force or company.br_slug is None
    try:
        page = _get_page(db, url, must_fetch, session=session)
    except (LookupError, polite_http.FetchError, requests.RequestException) as exc:
        logger.warning("profile refresh failed for %s: %s", company.ticker, exc)
        summary["profile"] = f"error: {exc}"
        return ProfileRefreshResult()
    if page is None:
        summary["profile"] = "cached"
        cached_version = db.scalar(
            select(DocumentVersion)
            .join(
                SourceDocument,
                DocumentVersion.source_document_id == SourceDocument.id,
            )
            .where(
                SourceDocument.company_id == company.id,
                SourceDocument.source_name == "biznesradar",
                SourceDocument.source_type == "company_profile",
                SourceDocument.scope_key == "current",
            )
            .order_by(DocumentVersion.id.desc())
            .limit(1)
        )
        if cached_version is not None:
            cached_profile = biznesradar.parse_profile(
                cached_version.raw_content, company.ticker
            )
            schedule_id = _record_report_calendar(
                db,
                company=company,
                source_version=cached_version,
                profile=cached_profile,
                summary=summary,
            )
            return ProfileRefreshResult(
                source_version_id=cached_version.id,
                report_schedule_id=schedule_id,
            )
        return ProfileRefreshResult()

    recorded = _record_page_evidence(
        db,
        company,
        page,
        source_type="company_profile",
        scope_key="current",
    )
    try:
        profile = biznesradar.parse_profile(page.text, company.ticker)
        for field_name, fact_key in fields.COMPANY_SCALAR_FACT_KEYS.items():
            evidence.record_numeric_fact(
                db,
                company,
                recorded.version,
                fact_type="company_scalar",
                fact_key=fact_key,
                value=getattr(profile, field_name),
                unit=fields.COMPANY_SCALAR_UNITS[field_name],
                period="current",
                locator={
                    "page": "profile",
                    "field": field_name,
                    "source_label": {
                        "shares_outstanding": "Liczba akcji",
                        "market_cap": "Kapitalizacja",
                        "enterprise_value": "Enterprise Value",
                    }[field_name],
                },
                extractor_version=PROFILE_SCALAR_EXTRACTOR_VERSION,
            )
        evidence.mark_parse_result(recorded.version, success=True)
    except biznesradar.ParseError as exc:
        evidence.mark_parse_result(recorded.version, success=False, error=str(exc))
        logger.warning("profile parse failed for %s: %s", company.ticker, exc)
        summary["profile"] = f"error: {exc}"
        return ProfileRefreshResult(source_version_id=recorded.version.id)

    company.name = profile.name or company.name
    company.br_slug = profile.slug or company.br_slug
    company.sector = profile.sector or company.sector
    company.market = profile.market or company.market
    company.shares_outstanding = profile.shares_outstanding or company.shares_outstanding
    # Reported market cap/EV (PLN) — authoritative for size classification.
    company.market_cap = profile.market_cap or company.market_cap
    company.enterprise_value = profile.enterprise_value or company.enterprise_value
    schedule_id = _record_report_calendar(
        db,
        company=company,
        source_version=recorded.version,
        profile=profile,
        summary=summary,
    )
    _merge_premium_nodes(db, company, page.text)
    detail = "ok" if company.br_slug else "ok (no slug — using ticker)"
    if profile.market_cap is not None:
        detail += f" (mcap {profile.market_cap / 1e6:,.0f} mln zł)".replace(",", " ")
    summary["profile"] = detail
    return ProfileRefreshResult(
        price=profile.price,
        source_version_id=recorded.version.id,
        report_schedule_id=schedule_id,
    )


def _record_report_calendar(
    db: Session,
    *,
    company: Company,
    source_version: DocumentVersion,
    profile: biznesradar.CompanyProfile,
    summary: dict[str, str],
) -> int | None:
    try:
        schedule = report_calendar.record_profile_schedule(
            db,
            company=company,
            source_version=source_version,
            report_date=profile.next_report_date,
            report_label=profile.next_report_label,
            parse_error=profile.next_report_parse_error,
        )
    except report_calendar.ReportCalendarError as exc:
        summary["report_calendar"] = f"error: {exc}"
        return None
    _summarize_report_calendar(schedule=schedule, summary=summary)
    return schedule.id


def _summarize_report_calendar(
    *, schedule, summary: dict[str, str]
) -> None:
    if schedule.source_status == "scheduled":
        summary["report_calendar"] = (
            f"ok ({schedule.report_date.isoformat()}; {schedule.automation_status})"
        )
    else:
        summary["report_calendar"] = (
            f"gap: {schedule.automation_reason or 'brak daty następnego raportu'}"
        )


# Forecast rows whose value is money (mln zł on the page, already converted
# to tys. PLN by parse_forecasts) vs a plain percent/ratio — decides which
# unit tag lands in CompanyMarketData.forecast_consensus / advanced_metrics.
_FORECAST_MONEY_UNITS = {
    "revenue": "tys. PLN",
    "ebitda": "tys. PLN",
    "operating_profit": "tys. PLN",
    "net_income": "tys. PLN",
    "capex": "tys. PLN",
    "depreciation": "tys. PLN",
    "ebitda_margin_pct": "%",
    "operating_margin_pct": "%",
    "net_margin_pct": "%",
    "pe": "x",
}
_FORECAST_CONSENSUS_GROWTH_METRICS = {
    "revenue",
    "ebitda",
    "operating_profit",
    "net_income",
    "capex",
    "depreciation",
}
# O4K (TTM) rows worth keeping as their own advanced_metrics entry — feeds
# scenarios.ScenarioInputs.ebitda_ttm (EV/EBITDA scenarios for energy names)
# plus two adjacent TTM facts the AI prompt can use as-is.
_FORECAST_TTM_METRICS = ("ebitda", "capex", "depreciation")


def _upsert_forecasts(
    db: Session,
    company: Company,
    table: biznesradar.ForecastTable,
    *,
    source_version_id: int,
    source_as_of: datetime,
) -> tuple[list[str], list[str]]:
    """Merge a parsed /prognozy table into CompanyMarketData.

    Reuses market_data.merge_premium_market_data (same merge semantics as the
    premium-session path) so both sources stay compatible: konsensus columns
    -> forecast_consensus[year][metric], the O4K column's
    ebitda/capex/depreciation -> advanced_metrics as *_ttm facts. Returns
    (consensus years written, ttm metric keys written) for the summary line.
    """
    forecast_consensus: dict[str, dict[str, dict]] = {}
    ttm_metrics: dict[str, dict] = {}
    ttm_column_index = next(
        (i for i, c in enumerate(table.columns) if c.kind == "raport_ttm"), None
    )

    for row in table.rows:
        if row.metric is None:
            continue
        previous_annual_value: float | None = None
        previous_annual_period: str | None = None
        for column, value, estimate_range in zip(
            table.columns, row.values, row.estimate_ranges, strict=True
        ):
            if value is None:
                continue
            if column.kind == "raport":
                previous_annual_value = value
                previous_annual_period = column.label
                continue
            if column.kind != "konsensus":
                continue
            metric_payload = {
                "value": value,
                "unit": _FORECAST_MONEY_UNITS.get(row.metric, ""),
                "source": "biznesradar_forecasts",
                "source_document_version_id": source_version_id,
                "source_as_of": source_as_of.isoformat(),
                "period_kind": "fiscal_year",
                "growth_pct": (
                    round((value / previous_annual_value - 1.0) * 100.0, 2)
                    if previous_annual_value not in {None, 0}
                    else None
                ),
                "growth_base_period": previous_annual_period,
            }
            if row.metric == "pe":
                metric_payload.update(
                    {
                        "semantic": "forward_trading_multiple",
                        "derived_from": "current_market_cap / forecast_net_income",
                        "not_a_target_multiple": True,
                    }
                )
            if estimate_range is not None:
                metric_payload["forecast_count"] = estimate_range.forecast_count
                metric_payload["range_min"] = estimate_range.minimum
                metric_payload["range_max"] = estimate_range.maximum
            forecast_consensus.setdefault(column.label, {})[row.metric] = metric_payload
            previous_annual_value = value
            previous_annual_period = column.label
        if (
            ttm_column_index is not None
            and row.metric in _FORECAST_TTM_METRICS
            and ttm_column_index < len(row.values)
            and row.values[ttm_column_index] is not None
        ):
            ttm_metrics[f"{row.metric}_ttm"] = {
                "value": row.values[ttm_column_index],
                "unit": "tys. PLN",
                "source": "biznesradar_forecasts_o4k",
            }

    market_data.replace_forecast_consensus(db, company, forecast_consensus)
    if ttm_metrics:
        market_data.merge_premium_market_data(
            db,
            company,
            {"advanced_metrics": ttm_metrics},
        )
    return sorted(forecast_consensus.keys()), sorted(ttm_metrics.keys())


def _refresh_forecasts(
    db: Session,
    company: Company,
    force: bool,
    summary: dict[str, str],
    session: requests.Session | None = None,
) -> None:
    """Analyst forecasts (/prognozy/{slug}).

    VERIFIED live 2026-07-11: the table structure is public, but consensus
    values are blank anonymously and populated by an authenticated Premium
    session. We still fetch the anonymous shape when credentials are absent so
    missingness is explicit; a collector that promises consensus coverage must
    require and report successful Premium authentication.

    `_merge_premium_nodes` runs first (same as every other fetched BR page)
    so any ROIC/FCF/EV/dividend-coverage node BiznesRadar happens to render
    on this page is still picked up. The URL is identical for anonymous and
    Premium sessions, while the value visibility differs.
    """
    url = biznesradar.page_url("forecasts", _report_slug(company))
    try:
        page = _get_page(db, url, force, session=session)
    except (LookupError, polite_http.FetchError, requests.RequestException) as exc:
        logger.warning("forecasts refresh failed for %s: %s", company.ticker, exc)
        summary["forecasts"] = f"error: {exc}"
        return
    if page is None:
        summary["forecasts"] = "cached"
        return

    _merge_premium_nodes(db, company, page.text)
    recorded = _record_page_evidence(
        db,
        company,
        page,
        source_type="analyst_forecast",
        scope_key="consensus",
    )
    try:
        table = biznesradar.parse_forecasts(page.text)
    except biznesradar.ParseError as exc:
        evidence.mark_parse_result(recorded.version, success=False, error=str(exc))
        logger.warning("forecasts parse failed for %s: %s", company.ticker, exc)
        summary["forecasts"] = f"error: {exc}"
        return

    consensus_years, ttm_keys = _upsert_forecasts(
        db,
        company,
        table,
        source_version_id=recorded.version.id,
        source_as_of=recorded.version.fetched_at,
    )
    for row in table.rows:
        if row.metric is None:
            continue
        previous_annual_value: float | None = None
        previous_annual_period: str | None = None
        for column, value, estimate_range in zip(
            table.columns, row.values, row.estimate_ranges, strict=True
        ):
            if value is None:
                continue
            if column.kind == "raport":
                previous_annual_value = value
                previous_annual_period = column.label
                continue
            if column.kind != "konsensus":
                continue
            locator = {
                "url": page.effective_url,
                "table": "profile-forecast",
                "row": row.label,
                "column": column.label,
                "statistic": "consensus",
                "semantic": (
                    "market_context_only"
                    if row.metric == "pe"
                    else "analyst_expectation"
                ),
                "not_a_target_multiple": row.metric == "pe",
                "coverage_window_months": 6,
            }
            value_key = (
                "market_implied.forward_pe"
                if row.metric == "pe"
                else f"consensus.{row.metric}.value"
            )
            evidence.record_numeric_fact(
                db,
                company,
                recorded.version,
                fact_type=(
                    "market_context" if row.metric == "pe" else "analyst_forecast"
                ),
                fact_key=value_key,
                value=value,
                unit=_FORECAST_MONEY_UNITS.get(row.metric, ""),
                period=column.label,
                locator=locator,
                extractor_version="biznesradar-forecasts@2",
            )
            if (
                row.metric in _FORECAST_CONSENSUS_GROWTH_METRICS
                and previous_annual_value not in {None, 0}
            ):
                evidence.record_numeric_fact(
                    db,
                    company,
                    recorded.version,
                    fact_type="analyst_forecast",
                    fact_key=f"consensus.{row.metric}.growth_pct",
                    value=round((value / previous_annual_value - 1.0) * 100.0, 4),
                    unit="%",
                    period=column.label,
                    locator={
                        **locator,
                        "statistic": "growth_pct",
                        "growth_base_period": previous_annual_period,
                    },
                    extractor_version="biznesradar-forecasts@2",
                )
            if estimate_range is not None and row.metric != "pe":
                for suffix, range_value, unit in (
                    ("low", estimate_range.minimum, _FORECAST_MONEY_UNITS.get(row.metric, "")),
                    ("high", estimate_range.maximum, _FORECAST_MONEY_UNITS.get(row.metric, "")),
                    ("forecast_count", estimate_range.forecast_count, "count"),
                ):
                    evidence.record_numeric_fact(
                        db,
                        company,
                        recorded.version,
                        fact_type="analyst_forecast",
                        fact_key=f"consensus.{row.metric}.{suffix}",
                        value=range_value,
                        unit=unit,
                        period=column.label,
                        locator={**locator, "statistic": suffix},
                        extractor_version="biznesradar-forecasts@2",
                    )
            previous_annual_value = value
            previous_annual_period = column.label
    evidence.mark_parse_result(recorded.version, success=True)
    consensus_columns = [c.label for c in table.columns if c.kind == "konsensus"]
    if consensus_years:
        detail = f"ok ({', '.join(consensus_years)} consensus)"
    elif consensus_columns:
        detail = (
            "ok (kolumny konsensusu bez wartości: "
            f"{', '.join(consensus_columns)})"
        )
    else:
        detail = "ok (brak kolumn konsensusu)"
    if ttm_keys:
        detail += f"; O4K: {', '.join(ttm_keys)}"
    if table.unmapped_labels:
        shown = ", ".join(sorted(set(table.unmapped_labels))[:4])
        more_count = len(set(table.unmapped_labels)) - 4
        more = f" +{more_count}" if more_count > 0 else ""
        detail += f"; pominięte: {shown}{more}"
    summary["forecasts"] = detail


def _table_detail(table: biznesradar.ReportTable) -> str:
    """Technical detail for the status panel: shape + period range."""
    if not table.periods:
        return "; 0 periods!"
    return (
        f"; {len(table.rows)} rows \u00d7 {len(table.periods)} periods; "
        f"{table.periods[0]}\u2013{table.periods[-1]}"
    )


def _grid_warning(table: biznesradar.ReportTable) -> str:
    """Flag quarterly tables that look like condensed annual columns
    (~one period per year) — the 'data is not fully queried' symptom."""
    if table.freq != "Q" or len(table.periods) < 6:
        return ""
    years = {period[:4] for period in table.periods}
    if len(years) >= 0.8 * len(table.periods):
        return " — uwaga: kolumny wyglądają na roczne, nie kwartalne"
    return ""


def _refresh_reports(
    db: Session,
    company: Company,
    force: bool,
    summary: dict[str, str],
    session: requests.Session | None = None,
) -> None:
    for kind, (statement, freq) in REPORT_PAGES.items():
        url = biznesradar.page_url(kind, _report_slug(company))
        try:
            page = _get_page(db, url, force, session=session)
            if page is None:
                summary[kind] = "cached"
                continue
            _merge_premium_nodes(db, company, page.text)
            recorded = _record_page_evidence(
                db,
                company,
                page,
                source_type="financial_report",
                scope_key=kind,
            )
            try:
                table = biznesradar.parse_report_table(page.text, freq)
                _require_usable_grid(table)
            except biznesradar.ParseError as exc:
                evidence.mark_parse_result(recorded.version, success=False, error=str(exc))
                raise
            evidence.mark_parse_result(recorded.version, success=True)
            count = _upsert_report_values(
                db,
                company,
                statement,
                table,
                recorded.version,
                replace=force,
            )
            summary[kind] = f"ok ({count} values{_table_detail(table)}){_grid_warning(table)}"
        except (
            polite_http.FetchError,
            biznesradar.ParseError,
            LookupError,
            requests.RequestException,
        ) as exc:
            logger.warning("%s refresh failed for %s: %s", kind, company.ticker, exc)
            summary[kind] = f"error: {exc}"


def _refresh_indicators(
    db: Session,
    company: Company,
    force: bool,
    summary: dict[str, str],
    session: requests.Session | None = None,
) -> None:
    for kind in INDICATOR_PAGES:
        url = biznesradar.page_url(kind, _report_slug(company))
        try:
            page = _get_page(db, url, force, session=session)
            if page is None:
                summary[kind] = "cached"
                continue
            _merge_premium_nodes(db, company, page.text)
            recorded = _record_page_evidence(
                db,
                company,
                page,
                source_type="market_indicators",
                scope_key=kind,
            )
            try:
                table = biznesradar.parse_report_table(page.text, freq="Q")
                _require_usable_grid(table)
            except biznesradar.ParseError as exc:
                evidence.mark_parse_result(recorded.version, success=False, error=str(exc))
                raise
            evidence.mark_parse_result(recorded.version, success=True)
            count, unmapped = _upsert_indicators(
                db, company, table, recorded.version
            )
            note = ""
            if unmapped:
                shown = ", ".join(sorted(unmapped)[:4])
                more = f" +{len(unmapped) - 4}" if len(unmapped) > 4 else ""
                note = f"; pominięte: {shown}{more}"
            summary[kind] = f"ok ({count} values{_table_detail(table)}{note})"
        except (
            polite_http.FetchError,
            biznesradar.ParseError,
            LookupError,
            requests.RequestException,
        ) as exc:
            logger.warning("%s refresh failed for %s: %s", kind, company.ticker, exc)
            summary[kind] = f"error: {exc}"


def _refresh_dividends(
    db: Session,
    company: Company,
    force: bool,
    summary: dict[str, str],
    session: requests.Session | None = None,
) -> None:
    url = biznesradar.page_url("dividends", _report_slug(company))
    try:
        page = _get_page(db, url, force, session=session)
        if page is None:
            summary["dividends"] = "cached"
            return
        _merge_premium_nodes(db, company, page.text)
        entries = biznesradar.parse_dividends(page.text)
        count = _upsert_dividends(db, company, entries)
        summary["dividends"] = f"ok ({count} years)"
    except LookupError:
        summary["dividends"] = "none (no dividend page)"  # plenty of companies never paid
    except (
        polite_http.FetchError,
        biznesradar.ParseError,
        requests.RequestException,
    ) as exc:
        logger.warning("dividends refresh failed for %s: %s", company.ticker, exc)
        summary["dividends"] = f"error: {exc}"


def _fetch_br_history(
    db: Session,
    company: Company,
    session: requests.Session | None = None,
) -> RecordedPriceHistory:
    """Archiwum notowań, PAGE 1 ONLY (~50 most recent sessions).

    robots.txt allows the first page and disallows the `,N` paginated views —
    the app therefore never paginates. 50 sessions cover every incremental
    top-up and give a usable degraded history when deep sources are down.
    """
    url = biznesradar.page_url("price_history", _report_slug(company))
    response = polite_http.fetch(url, session=session)
    fetch_log = _log_fetch(db, url, response.status_code)
    if response.status_code == 404:
        raise LookupError(f"404 for {url}")
    response.raise_for_status()
    content = getattr(response, "content", None) or response.text.encode("utf-8")
    headers = getattr(response, "headers", {}) or {}
    page = FetchedPage(
        text=response.text,
        content=content,
        requested_url=url,
        effective_url=str(getattr(response, "url", None) or url),
        status_code=response.status_code,
        mime_type=headers.get("content-type", "text/html").split(";", 1)[0].strip(),
        fetched_at=fetch_log.fetched_at,
        fetch_log=fetch_log,
    )
    recorded = _record_page_evidence(
        db,
        company,
        page,
        source_type="price_history",
        scope_key="raw-close",
    )
    try:
        bars = biznesradar.parse_price_history(response.text)
        evidence.mark_parse_result(recorded.version, success=True)
    except biznesradar.ParseError as exc:
        evidence.mark_parse_result(recorded.version, success=False, error=str(exc))
        raise
    return RecordedPriceHistory(
        bars=bars,
        source_version_id=recorded.version.id,
        fetched_at=recorded.version.fetched_at,
    )


def _refresh_prices(
    db: Session,
    company: Company,
    fallback_price: float | None = None,
    fallback_source_version_id: int | None = None,
    session: requests.Session | None = None,
) -> str:
    """BiznesRadar-only price refresh.

    The old external CSV chain was noisy in production. We now use the
    robots-allowed BiznesRadar history page first, then the already-fetched
    profile quote as a one-row fallback when history is unavailable.

    Self-healing: future-dated rows (an old bug wrote them; they froze the
    chain forever via the `last_day >= today` guard) are purged up front.
    """
    today = date.today()
    scraped_at = utcnow()
    purged_future = (
        db.execute(
            delete(Price).where(Price.company_id == company.id, Price.date > today)
        ).rowcount
        or 0
    )

    rows_count = int(
        db.scalar(
            select(func.count()).select_from(Price).where(Price.company_id == company.id)
        )
        or 0
    )
    last_day = db.scalar(
        select(Price.date)
        .where(Price.company_id == company.id)
        .order_by(Price.date.desc())
        .limit(1)
    )
    backfill = rows_count < MIN_PRICE_HISTORY_ROWS

    if not backfill and last_day is not None and last_day >= today:
        # Asking any source for dates after today is both noisy and useless.
        # Zero requests instead.
        return f"ok (aktualne; {rows_count} dni w bazie)"

    bars: list[biznesradar.PriceBar] | None = None
    source_version_id: int | None = None
    source = ""
    errors: list[str] = []

    def try_br_history() -> None:
        nonlocal bars, scraped_at, source, source_version_id
        try:
            history = _fetch_br_history(db, company, session=session)
            if history.bars:
                bars = history.bars
                source_version_id = history.source_version_id
                scraped_at = history.fetched_at
                source = "BR archiwum"
            else:
                errors.append("br-archiwum: pusta tabela")
        except (
            polite_http.FetchError,
            biznesradar.ParseError,
            LookupError,
            requests.RequestException,
        ) as exc:
            errors.append(f"br-archiwum: {exc}")

    try_br_history()

    if not bars:
        logger.warning(
            "price refresh failed for %s: %s", company.ticker, " | ".join(errors)
        )
        # Last resort: today's quote scraped from the (already fetched)
        # BiznesRadar profile page — keeps kurs/mcap/C-Z alive.
        if fallback_price is not None:
            if last_day is None or last_day < today:
                db.add(
                    Price(
                        company_id=company.id,
                        source_version_id=fallback_source_version_id,
                        date=today,
                        close=fallback_price,
                        source_name="biznesradar_profile",
                        series_key=f"biznesradar:{company.ticker}:raw-close",
                        basis_version="br-profile@1",
                        adjustment_status="raw_unverified",
                        scraped_at=scraped_at,
                    )
                )
            return (
                "ok (fallback: 1 dzien, kurs z profilu BiznesRadar; historia "
                "niedostepna: " + " | ".join(errors)[:160] + ")"
            )
        return f"error: {' | '.join(errors)}"

    if backfill and rows_count:
        # replace the stub row(s) so history is complete and duplicate-free
        db.execute(delete(Price).where(Price.company_id == company.id))
        last_day = None

    assert source_version_id is not None
    existing_by_day = {
        row.date: row
        for row in db.scalars(
            select(Price).where(
                Price.company_id == company.id,
                Price.date.in_([bar.day for bar in bars if bar.day <= today]),
            )
        )
    }
    added = 0
    rebound = 0
    for bar in bars:
        if bar.day > today:
            continue  # never store the future again (see purge above)
        existing = existing_by_day.get(bar.day)
        if existing is not None:
            if existing.source_version_id != source_version_id:
                rebound += 1
            existing.close = bar.close
            existing.volume = bar.volume
            existing.source_version_id = source_version_id
            existing.source_name = "biznesradar_history"
            existing.series_key = f"biznesradar:{company.ticker}:raw-close"
            existing.basis_version = "br-price-history@1"
            existing.adjustment_status = "raw_unverified"
            existing.scraped_at = scraped_at
            continue
        db.add(
            Price(
                company_id=company.id,
                source_version_id=source_version_id,
                date=bar.day,
                close=bar.close,
                volume=bar.volume,
                source_name="biznesradar_history",
                series_key=f"biznesradar:{company.ticker}:raw-close",
                basis_version="br-price-history@1",
                adjustment_status="raw_unverified",
                scraped_at=scraped_at,
            )
        )
        added += 1

    purge_note = f"; usunieto {purged_future} przyszlych dat" if purged_future else ""
    if added:
        first_day = min(bar.day for bar in bars)
        newest_day = max(bar.day for bar in bars)
        return (
            f"ok ({added} new days; {first_day}\u2013{newest_day}; "
            f"zrodlo: {source}{purge_note})"
        )
    rebound_note = f"; powiazano {rebound} istniejacych dni" if rebound else ""
    return f"ok (0 new days{rebound_note}; zrodlo: {source}{purge_note})"
