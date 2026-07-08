"""Record real BiznesRadar pages as test fixtures (run on YOUR machine).

The committed fixtures are synthetic (structure mirrors the reference scraper's
verified markup). Replace them with real pages once, then re-run pytest — that
is task P1.1:

    cd backend
    python scripts/record_fixtures.py DEC

Uses the same polite rate-limited fetcher as the app, so this takes ~30 s.
If a parser test fails afterwards, the site's markup changed — fix
app/scrapers/biznesradar.py (and only it), not the tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scrapers import biznesradar
from app.scrapers import http as polite_http

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

# Real pages are stored under real_* names: synthetic fixtures (exact-value
# tests) stay untouched, while structural tests pick real_* up automatically.
PAGE_TO_FIXTURE = {
    "profile": "real_br_profile.html",
    "income_q": "real_br_income_q.html",
    "income_y": "real_br_income_y.html",
    "balance_q": "real_br_balance_q.html",
    "cashflow_q": "real_br_cashflow_q.html",
    "indicators_value": "real_br_indicators_value.html",
    "indicators_profitability": "real_br_indicators_profitability.html",
    "dividends": "real_br_dividend.html",
    # Archiwum notowań — price-history source (page 1 only; robots.txt
    # disallows the ,N paginated views, so only page 1 is ever recorded).
    "price_history": "real_br_price_history.html",
}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    ticker = sys.argv[1].upper()

    for kind, filename in PAGE_TO_FIXTURE.items():
        url = biznesradar.page_url(kind, ticker)
        print(f"fetching {url} ...", flush=True)
        response = polite_http.fetch(url)
        if response.status_code != 200:
            print(f"  -> HTTP {response.status_code}, skipped")
            continue
        (FIXTURES_DIR / filename).write_text(response.text, encoding="utf-8")
        print(f"  -> {filename} ({len(response.text)} bytes)")

    print("\nDone. Now run: pytest tests/test_biznesradar_parser.py -v")
    print("Structural tests over real_* fixtures activate automatically;")
    print("if one fails, the site's markup changed — fix the parser module.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
