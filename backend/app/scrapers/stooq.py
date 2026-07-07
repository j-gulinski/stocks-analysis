"""Daily price history from stooq — a plain CSV download, no scraping needed.

Production finding (SNT): the history endpoint can answer HTTP 404 even for
valid tickers. Strategy: try the history CSV on both hosts (.pl, .com); if
that fails, fall back to the current-quote CSV, which still yields today's
close — enough for kurs, market cap and C/Z TTM while charts degrade
gracefully. Errors carry every attempted URL so the refresh summary says
exactly what happened.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from urllib.parse import urlencode

import requests

from app.scrapers import http as polite_http
# Shared daily-bar shape lives with the primary scraper; re-exported here so
# existing imports (yahoo, refresh, tests) keep working unchanged.
from app.scrapers.biznesradar import PriceBar  # noqa: F401

HOSTS = ("https://stooq.pl", "https://stooq.com")


class PriceDataError(Exception):
    pass


class StooqLimitError(PriceDataError):
    """Daily hit limit / access denied — retrying other endpoints is pointless
    and impolite; the caller should fall back to another price source."""


_LIMIT_MARKERS = (
    "przekroczono dzienny limit",
    "exceeded the daily hits limit",
    "access denied",
    "brak dostepu",
    "brak dostępu",
)


def _check_body_limits(text: str) -> None:
    lowered = text.strip().lower()[:200]
    for marker in _LIMIT_MARKERS:
        if marker in lowered:
            raise StooqLimitError(
                "stooq odmówił dostępu (limit dzienny / access denied) — "
                "kurs zostanie pobrany z profilu BiznesRadar; historia jutro."
            )




def daily_csv_url(ticker: str, start: date | None = None, host: str = HOSTS[0]) -> str:
    params: dict[str, str] = {"s": ticker.lower(), "i": "d"}
    if start is not None:
        params["d1"] = start.strftime("%Y%m%d")
    return f"{host}/q/d/l/?{urlencode(params)}"


def quote_csv_url(ticker: str, host: str = HOSTS[0]) -> str:
    # f=sd2t2ohlcv → symbol, date, time, OHLC, volume; h → header; e=csv
    return f"{host}/q/l/?s={ticker.lower()}&f=sd2t2ohlcv&h&e=csv"


def _column_index(header: list[str], *prefixes: str) -> int | None:
    for i, name in enumerate(header):
        if any(name.startswith(p) for p in prefixes):
            return i
    return None


def parse_prices_csv(text: str) -> list[PriceBar]:
    """Parse the history CSV. Header may be Polish or English."""
    stripped = text.strip()
    if not stripped or "brak danych" in stripped.lower():
        return []

    reader = csv.reader(io.StringIO(stripped))
    try:
        header = [column.strip().lower() for column in next(reader)]
    except StopIteration:
        return []

    date_idx = _column_index(header, "data", "date")
    close_idx = _column_index(header, "zamkni", "close")
    volume_idx = _column_index(header, "wolumen", "volume")
    if date_idx is None or close_idx is None:
        raise PriceDataError(f"Unrecognized CSV header: {header}")

    bars: list[PriceBar] = []
    for row in reader:
        if len(row) <= close_idx:
            continue
        try:
            day = date.fromisoformat(row[date_idx].strip())
            close = float(row[close_idx])
        except ValueError:
            continue  # malformed row — skip, don't fail the whole import
        volume: int | None = None
        if volume_idx is not None and len(row) > volume_idx:
            try:
                volume = int(float(row[volume_idx]))
            except ValueError:
                volume = None
        bars.append(PriceBar(day=day, close=close, volume=volume))
    return bars


def parse_quote_csv(text: str) -> PriceBar | None:
    """Parse the single-row current-quote CSV (symbol,date,time,o,h,l,c,v)."""
    bars = parse_prices_csv(text)  # same column detection works here
    return bars[-1] if bars else None


def fetch_daily_prices(
    ticker: str,
    start: date | None = None,
    session: requests.Session | None = None,
) -> list[PriceBar]:
    attempts: list[str] = []

    for host in HOSTS:
        url = daily_csv_url(ticker, start, host)
        response = polite_http.fetch(url, session=session)
        if response.status_code == 200:
            _check_body_limits(response.text)  # raises → stop hammering stooq
            bars = parse_prices_csv(response.text)
            if bars:
                return bars
            attempts.append(f"{url} -> empty CSV")
        else:
            attempts.append(f"{url} -> HTTP {response.status_code}")

    # Fallback: current quote only (keeps kurs/mcap alive without history).
    for host in HOSTS:
        url = quote_csv_url(ticker, host)
        response = polite_http.fetch(url, session=session)
        if response.status_code == 200:
            _check_body_limits(response.text)
            bar = parse_quote_csv(response.text)
            if bar is not None:
                if start is not None and bar.day < start:
                    return []  # nothing newer than what we already have
                return [bar]
            attempts.append(f"{url} -> unparsable")
        else:
            attempts.append(f"{url} -> HTTP {response.status_code}")

    raise PriceDataError("all stooq endpoints failed: " + "; ".join(attempts))
