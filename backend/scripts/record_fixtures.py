"""Record replayable BiznesRadar fixtures for one company.

Run from ``backend/`` on a machine allowed to reach BiznesRadar:

    python scripts/record_fixtures.py SNT --expected-market GPW

The profile is fetched first and its canonical slug is required before any
report URL is built. Record a second, explicitly verified NewConnect company in
the same way; ticker-specific directories prevent one capture overwriting the
other. All requests use the application's polite fetcher.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scrapers import biznesradar
from app.scrapers import http as polite_http

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
REAL_BR_DIR = FIXTURES_DIR / "real" / "br"

PAGE_TO_FILENAME = {
    "profile": "profile.html",
    "income_q": "income_q.html",
    "income_y": "income_y.html",
    "balance_q": "balance_q.html",
    "cashflow_q": "cashflow_q.html",
    "indicators_value": "indicators_value.html",
    "indicators_profitability": "indicators_profitability.html",
    "dividends": "dividends.html",
    # Page 1 only: robots.txt disallows /notowania-historyczne/*,* pagination.
    "price_history": "price_history.html",
}


def recording_plan(ticker: str, profile_html: str) -> tuple[dict, dict[str, str]]:
    """Return parsed metadata and slug-safe URLs; pure for regression tests."""
    ticker = ticker.upper()
    profile = biznesradar.parse_profile(profile_html, ticker)
    if not profile.slug:
        raise ValueError(
            f"Profile for {ticker} did not expose a canonical BiznesRadar slug; "
            "abort before risking the ticker redirect trap."
        )
    urls = {"profile": biznesradar.page_url("profile", ticker)}
    urls.update(
        {
            kind: biznesradar.page_url(kind, profile.slug)
            for kind in PAGE_TO_FILENAME
            if kind != "profile"
        }
    )
    metadata = {
        "ticker": ticker,
        "slug": profile.slug,
        "name": profile.name,
        "market": profile.market,
    }
    return metadata, urls


def record_company(ticker: str, expected_market: str | None = None) -> int:
    ticker = ticker.upper()
    profile_url = biznesradar.page_url("profile", ticker)
    print(f"fetching {profile_url} ...", flush=True)
    profile_response = polite_http.fetch(profile_url)
    if profile_response.status_code != 200:
        print(f"profile HTTP {profile_response.status_code} — nothing saved")
        return 1

    try:
        metadata, urls = recording_plan(ticker, profile_response.text)
    except ValueError as exc:
        print(str(exc))
        return 1

    if expected_market:
        parsed_market = (metadata["market"] or "").casefold()
        if parsed_market != expected_market.casefold():
            print(
                f"market check failed: expected {expected_market}, parsed "
                f"{metadata['market'] or 'unknown'} — nothing saved"
            )
            return 1

    target_dir = REAL_BR_DIR / ticker
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / PAGE_TO_FILENAME["profile"]).write_text(
        profile_response.text, encoding="utf-8"
    )
    (target_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"  -> {ticker}/profile.html; canonical slug={metadata['slug']}; "
        f"market={metadata['market'] or 'unknown'}"
    )

    failed = False
    for kind, filename in PAGE_TO_FILENAME.items():
        if kind == "profile":
            continue
        url = urls[kind]
        print(f"fetching {url} ...", flush=True)
        response = polite_http.fetch(url)
        if response.status_code != 200:
            failed = True
            print(f"  -> HTTP {response.status_code}, not recorded")
            continue
        (target_dir / filename).write_text(response.text, encoding="utf-8")
        print(f"  -> {ticker}/{filename} ({len(response.text)} bytes)")

    print("\nRun: pytest tests/test_biznesradar_parser.py -v")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker")
    parser.add_argument(
        "--expected-market",
        choices=("GPW", "NewConnect"),
        help="abort if the profile does not explicitly confirm this market",
    )
    args = parser.parse_args(argv)
    return record_company(args.ticker, expected_market=args.expected_market)


if __name__ == "__main__":
    raise SystemExit(main())
