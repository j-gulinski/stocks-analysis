"""Refresh orchestration: scrape BiznesRadar + stooq for one company → upsert DB.

Responsibilities split (see PLAN §2): scrapers fetch and parse, THIS service
owns persistence, caching and error isolation. One failed page never fails a
whole refresh — the summary tells the UI exactly what happened per page.
"""
from __future__ import annotations

import logging
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
    IndicatorValue,
    Price,
    ReportValue,
    utcnow,
)
from app.scrapers import biznesradar, stooq, yahoo
from app.scrapers import http as polite_http
from app.services import fields

# report pages: kind -> (statement, freq)
REPORT_PAGES: dict[str, tuple[str, str]] = {
    "income_q": ("income", "Q"),
    "income_y": ("income", "Y"),
    "balance_q": ("balance", "Q"),
    "cashflow_q": ("cashflow", "Q"),
}
INDICATOR_PAGES = ("indicators_value", "indicators_profitability")
# Below this many stored price rows the app has no real history and a
# successful provider fetch REPLACES what is there (backfill).
MIN_PRICE_HISTORY_ROWS = 30


class UnknownTickerError(Exception):
    """Ticker not found on BiznesRadar and unknown locally."""


def get_or_create_company(db: Session, ticker: str) -> Company:
    ticker = ticker.strip().upper()
    company = db.scalar(select(Company).where(Company.ticker == ticker))
    if company is None:
        company = Company(ticker=ticker)
        db.add(company)
        db.flush()  # assign id without committing the transaction yet
    return company


# ------------------------------------------------------------ fetch helpers

def _log_fetch(db: Session, url: str, status: int | None) -> None:
    db.add(FetchLog(url=url, status=status))


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


def _get_page(db: Session, url: str, force: bool) -> str | None:
    """Fetch a page through the polite client; None means 'use cache / skip'."""
    if not force and _is_fresh(db, url):
        return None
    response = polite_http.fetch(url)
    _log_fetch(db, url, response.status_code)
    if response.status_code == 404:
        raise LookupError(f"404 for {url}")
    response.raise_for_status()  # non-retryable, non-404 errors are real errors
    return response.text


# ------------------------------------------------------------------ upserts

def _upsert_report_values(
    db: Session,
    company: Company,
    statement: str,
    table: biznesradar.ReportTable,
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
            }

    if not rows_by_key:
        return 0

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
        },
    )
    db.execute(statement_insert)
    return len(rows_by_key)


def _upsert_indicators(
    db: Session, company: Company, table: biznesradar.ReportTable
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
    for row in table.rows:
        # Code-first (data-field survives label drift), label as fallback.
        code = fields.match_indicator(row.label, row.field_code)
        if code is None:
            unmapped.append(row.label)
            continue
        for period, value in zip(table.periods, row.values):
            record = existing.get((code, period))
            if record is None:
                record = IndicatorValue(
                    company_id=company.id, indicator=code, period=period, value=value
                )
                db.add(record)
                existing[(code, period)] = record
            else:
                record.value = value
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

    if scope in ("financials", "all"):
        profile_price = _refresh_profile(db, company, force, summary)
        _refresh_reports(db, company, force, summary)
        _refresh_indicators(db, company, force, summary)
        _refresh_dividends(db, company, force, summary)

        every_page_failed = all(
            status.startswith(("error", "none")) for status in summary.values()
        )
        if every_page_failed and company.name is None and not _has_any_data(db, company):
            db.commit()  # keep fetch_log entries for debugging
            raise UnknownTickerError(
                f"Ticker '{company.ticker}' not found on BiznesRadar "
                f"(all pages failed: {summary})."
            )

    if scope in ("prices", "all"):
        summary["prices"] = _refresh_prices(db, company, fallback_price=profile_price)

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


def _refresh_profile(
    db: Session, company: Company, force: bool, summary: dict[str, str]
) -> float | None:
    """Update company metadata; returns the current quote when the page shows
    one (used as the price source of last resort).

    Also resolves `br_slug` — without it every quarterly report URL would
    redirect to the annual view, so a missing slug overrides the page cache.
    """
    url = biznesradar.page_url("profile", company.ticker)
    must_fetch = force or company.br_slug is None
    try:
        html = _get_page(db, url, must_fetch)
    except (LookupError, polite_http.FetchError, requests.RequestException) as exc:
        logger.warning("profile refresh failed for %s: %s", company.ticker, exc)
        summary["profile"] = f"error: {exc}"
        return None
    if html is None:
        summary["profile"] = "cached"
        return None

    profile = biznesradar.parse_profile(html, company.ticker)
    company.name = profile.name or company.name
    company.br_slug = profile.slug or company.br_slug
    company.sector = profile.sector or company.sector
    company.market = profile.market or company.market
    company.shares_outstanding = profile.shares_outstanding or company.shares_outstanding
    # Reported market cap/EV (PLN) — authoritative for size classification.
    company.market_cap = profile.market_cap or company.market_cap
    company.enterprise_value = profile.enterprise_value or company.enterprise_value
    detail = "ok" if company.br_slug else "ok (no slug — using ticker)"
    if profile.market_cap is not None:
        detail += f" (mcap {profile.market_cap / 1e6:,.0f} mln zł)".replace(",", " ")
    summary["profile"] = detail
    return profile.price


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
    db: Session, company: Company, force: bool, summary: dict[str, str]
) -> None:
    for kind, (statement, freq) in REPORT_PAGES.items():
        url = biznesradar.page_url(kind, _report_slug(company))
        try:
            html = _get_page(db, url, force)
            if html is None:
                summary[kind] = "cached"
                continue
            table = biznesradar.parse_report_table(html, freq)
            count = _upsert_report_values(db, company, statement, table, replace=force)
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
    db: Session, company: Company, force: bool, summary: dict[str, str]
) -> None:
    for kind in INDICATOR_PAGES:
        url = biznesradar.page_url(kind, _report_slug(company))
        try:
            html = _get_page(db, url, force)
            if html is None:
                summary[kind] = "cached"
                continue
            table = biznesradar.parse_report_table(html, freq="Q")
            count, unmapped = _upsert_indicators(db, company, table)
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
    db: Session, company: Company, force: bool, summary: dict[str, str]
) -> None:
    url = biznesradar.page_url("dividends", _report_slug(company))
    try:
        html = _get_page(db, url, force)
        if html is None:
            summary["dividends"] = "cached"
            return
        entries = biznesradar.parse_dividends(html)
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
    db: Session, company: Company
) -> list[biznesradar.PriceBar]:
    """Archiwum notowań, PAGE 1 ONLY (~50 most recent sessions).

    robots.txt allows the first page and disallows the `,N` paginated views —
    the app therefore never paginates. 50 sessions cover every incremental
    top-up and give a usable degraded history when deep sources are down.
    """
    url = biznesradar.page_url("price_history", _report_slug(company))
    response = polite_http.fetch(url)
    _log_fetch(db, url, response.status_code)
    if response.status_code == 404:
        raise LookupError(f"404 for {url}")
    response.raise_for_status()
    return biznesradar.parse_price_history(response.text)


def _refresh_prices(
    db: Session, company: Company, fallback_price: float | None = None
) -> str:
    """Source chain, reworked after both CSV providers broke in production:

    - incremental (normal day): BiznesRadar archiwum page 1 (reliable, the
      same politely-fetched domain) → Yahoo → profile quote. stooq is
      SKIPPED here — it answers "access denied" to non-browser clients and
      hitting it daily after that signal would be impolite.
    - backfill (<MIN_PRICE_HISTORY_ROWS stored): Yahoo first (5y in one
      request when it works) → stooq (its one chance to recover) → BR
      archiwum page 1 (at least ~50 sessions) → profile quote.

    Self-healing: future-dated rows (an old bug wrote them; they froze the
    chain forever via the `last_day >= today` guard) are purged up front.
    """
    today = date.today()
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
        # Asking providers for tomorrow produced future d1= params and an
        # inverted Yahoo period1>period2 in production. Zero requests instead.
        return f"ok (aktualne; {rows_count} dni w bazie)"

    start = None if backfill else (last_day + timedelta(days=1) if last_day else None)

    bars: list[biznesradar.PriceBar] | None = None
    source = ""
    errors: list[str] = []

    def try_yahoo() -> None:
        nonlocal bars, source
        try:
            bars = yahoo.fetch_daily_prices(company.ticker, start=start)
            source = "Yahoo"
            _log_fetch(db, yahoo.chart_url(company.ticker, start), 200)
        except (
            polite_http.FetchError,
            yahoo.YahooError,
            requests.RequestException,
        ) as exc:
            errors.append(f"yahoo: {exc}")
            _log_fetch(db, yahoo.chart_url(company.ticker, start), None)

    def try_stooq() -> None:
        nonlocal bars, source
        try:
            bars = stooq.fetch_daily_prices(company.ticker, start=start)
            source = "stooq"
            _log_fetch(db, stooq.daily_csv_url(company.ticker, start), 200)
        except (
            polite_http.FetchError,
            stooq.PriceDataError,
            requests.RequestException,
        ) as exc:
            errors.append(f"stooq: {exc}")
            _log_fetch(db, stooq.daily_csv_url(company.ticker, start), None)

    def try_br_history() -> None:
        nonlocal bars, source
        try:
            history_bars = _fetch_br_history(db, company)
            if history_bars:
                bars = history_bars
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

    chain = (try_yahoo, try_stooq, try_br_history) if backfill else (try_br_history, try_yahoo)
    for attempt in chain:
        attempt()
        if bars:
            break

    if not bars:
        logger.warning(
            "price refresh failed for %s: %s", company.ticker, " | ".join(errors)
        )
        # Last resort: today's quote scraped from the (already fetched)
        # BiznesRadar profile page — keeps kurs/mcap/C-Z alive.
        if fallback_price is not None:
            if last_day is None or last_day < today:
                db.add(Price(company_id=company.id, date=today, close=fallback_price))
            return (
                "ok (fallback: 1 dzien, kurs z profilu BiznesRadar; historia "
                "niedostepna: " + " | ".join(errors)[:160] + ")"
            )
        return f"error: {' | '.join(errors)}"

    if backfill and rows_count:
        # replace the stub row(s) so history is complete and duplicate-free
        db.execute(delete(Price).where(Price.company_id == company.id))
        last_day = None

    added = 0
    for bar in bars:
        # date filters are inclusive and providers occasionally resend
        # history — guard against duplicate days at the app level too.
        if last_day is not None and bar.day <= last_day:
            continue
        if bar.day > today:
            continue  # never store the future again (see purge above)
        db.add(
            Price(company_id=company.id, date=bar.day, close=bar.close, volume=bar.volume)
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
    return f"ok (0 new days; zrodlo: {source}{purge_note})"
