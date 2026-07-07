"""Daily prices from Yahoo Finance — second source in the price chain.

GPW tickers live on Yahoo with a `.WA` suffix (SNT → SNT.WA). The v8 chart
endpoint returns JSON without any API key and tolerates polite scripted use;
requests still go through the shared rate-limited fetcher.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from urllib.parse import urlencode

import requests

from app.scrapers import http as polite_http
from app.scrapers.stooq import PriceBar  # shared shape across price sources

# query1 and query2 serve the same API; one sometimes rejects what the other
# accepts (regional edge behaviour) — both are tried in order.
CHART_HOSTS = (
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
)
CHART_ENDPOINT = f"{CHART_HOSTS[0]}/v8/finance/chart/"

# The v8 endpoint increasingly rejects requests that look non-browser-ish
# (401/429 with no crumb/cookie). Sending regular browser headers noticeably
# improves acceptance; a full cookie+crumb handshake stays out of scope —
# Yahoo is best-effort, BR archiwum is the reliable leg of the chain.
BROWSER_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://finance.yahoo.com/",
    "Origin": "https://finance.yahoo.com",
}


class YahooError(Exception):
    pass


def yahoo_symbol(ticker: str) -> str:
    return f"{ticker.upper()}.WA"


def chart_url(ticker: str, start: date | None = None, host: str = CHART_HOSTS[0]) -> str:
    params: dict[str, str] = {"interval": "1d"}
    if start is None:
        # 5y is plenty for the strategy's charts/median math and keeps the
        # initial pull light — Yahoo 429s aggressive first requests.
        params["range"] = "5y"
    else:
        period_start = datetime(
            start.year, start.month, start.day, tzinfo=timezone.utc
        )
        now_ts = int(datetime.now(timezone.utc).timestamp())
        start_ts = int(period_start.timestamp())
        # Defensive: an up-to-date DB once produced period1 > period2 (future
        # start date) and Yahoo answered 429s. Clamp to a sane window.
        if start_ts >= now_ts:
            start_ts = now_ts - 86_400
        params["period1"] = str(start_ts)
        params["period2"] = str(now_ts)
    return f"{host}/v8/finance/chart/{yahoo_symbol(ticker)}?{urlencode(params)}"


def parse_chart_json(text: str) -> list[PriceBar]:
    try:
        payload = json.loads(text)
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise YahooError(f"Unexpected Yahoo chart payload: {exc}") from exc

    bars: list[PriceBar] = []
    for index, ts in enumerate(timestamps):
        close = closes[index] if index < len(closes) else None
        if close is None:
            continue  # holidays / suspended sessions come back as nulls
        volume = volumes[index] if index < len(volumes) else None
        bars.append(
            PriceBar(
                day=datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                close=round(float(close), 4),
                volume=int(volume) if volume is not None else None,
            )
        )
    return bars


def fetch_daily_prices(
    ticker: str,
    start: date | None = None,
    session: requests.Session | None = None,
) -> list[PriceBar]:
    sess = session or requests.Session()
    sess.headers.update(BROWSER_HEADERS)
    attempts: list[str] = []
    for host in CHART_HOSTS:
        url = chart_url(ticker, start, host=host)
        try:
            response = polite_http.fetch(url, session=sess)
        except polite_http.FetchBlockedError as exc:
            # Hard stop after exhausted retries — the OTHER host will be
            # rate-limited too; respect the signal instead of doubling down.
            attempts.append(f"{url} -> {exc}")
            break
        except polite_http.FetchError as exc:
            attempts.append(f"{url} -> {exc}")
            continue
        if response.status_code != 200:
            attempts.append(f"{url} -> HTTP {response.status_code}")
            continue
        return parse_chart_json(response.text)
    raise YahooError("all Yahoo hosts failed: " + " | ".join(attempts))
