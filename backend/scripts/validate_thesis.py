"""WP4 validation harness — run the thesis pipeline OUTSIDE the DB (stage TH).

The sandbox has no Postgres, so this reconstructs exactly the *pure* half of
`dossier.build_dossier` from live BiznesRadar pages:

    profile → slug → income(Q) + balance(Q) + indicators(value/profitability)
    + dividends  →  fields.py mapping  →  metrics (quarters / TTM / P-E history /
    net cash / prescore)  →  insights.build_insights  →  thesis.build_thesis(MALIK)

ALL HTTP goes through `app/scrapers/http.py` (jittered per-domain limits). Pages
are cached to `backend/.cache/validation/` (gitignored) so re-runs never re-fetch
— politeness is non-negotiable. Report pages are fetched BY SLUG (the scraper-
doctor redirect trap: `/…/SNT,Q` → `/…/SYNEKTIK` silently drops `,Q`). Archiwum
notowań is NOT fetched here (the thesis needs no price history; the profile quote
is the price source), so there is zero pagination risk.

Usage (from backend/):  python scripts/validate_thesis.py SNT [--force]
Prints a JSON blob: parsed raw inputs (for hand-checking against the BR page) +
the deterministic thesis output. Deterministic engine only — no forecast outside
the DB, so valuation falls back to trailing TTM C/Z (stated in the output).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scrapers import biznesradar as br
from app.scrapers import http as polite_http
from app.services import fields, insights, metrics, thesis
from app.services.strategies import malik

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "validation"

# Pages the PURE pipeline needs. Cashflow + archiwum are deliberately omitted:
# net cash comes from the balance sheet and the thesis needs no price history,
# so we fetch the minimum (politeness). indicators_value carries the C/Z history
# (drives pe_vs_history); indicators_profitability carries ROE / margins.
REPORT_PAGES = ("income_q", "balance_q", "indicators_value",
                "indicators_profitability", "dividends")

_REQUESTS = {"count": 0}


def _fetch(kind: str, ticker: str, *, force: bool) -> str | None:
    """Polite fetch with a disk cache. Returns HTML or None on failure/redirect
    trouble. One retry is already baked into http.py's backoff — we never
    hammer past FetchBlockedError."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{ticker}_{kind}.html"
    if cache.exists() and not force:
        return cache.read_text(encoding="utf-8")
    url = br.page_url(kind, ticker)
    try:
        resp = polite_http.fetch(url)
    except polite_http.FetchBlockedError as exc:
        print(f"  ! {kind}: blocked — {exc}", file=sys.stderr)
        return None
    _REQUESTS["count"] += 1
    if resp.status_code != 200:
        print(f"  ! {kind}: HTTP {resp.status_code}", file=sys.stderr)
        return None
    cache.write_text(resp.text, encoding="utf-8")
    return resp.text


def _income_series(table: br.ReportTable) -> metrics.IncomeSeries:
    """Replicates dossier.load_income_series: highest-ranked row wins per
    (period, canonical field), then derive statement-variant gaps."""
    series: metrics.IncomeSeries = {}
    ranks: dict[tuple[str, str], int] = {}
    for row in table.rows:
        canonical = fields.match_income_field(row.label, row.field_code)
        if canonical is None:
            continue
        rank = fields.income_match_rank(canonical, row.label, row.field_code)
        for period, value in zip(table.periods, row.values):
            if value is None:
                continue
            key = (period, canonical)
            if key in ranks and ranks[key] >= rank:
                continue
            ranks[key] = rank
            series.setdefault(period, {})[canonical] = float(value)
    return metrics.derive_income_fields(series)


def _balance_latest(table: br.ReportTable) -> dict[str, float]:
    """Replicates dossier.load_balance_latest: canonical values at the newest
    period column."""
    if not table.periods:
        return {}
    latest_period = metrics.sort_periods(set(table.periods))[-1]
    col = table.periods.index(latest_period)
    latest: dict[str, float] = {}
    for row in table.rows:
        if col >= len(row.values) or row.values[col] is None:
            continue
        canonical = fields.match_balance_field(row.label, row.field_code)
        if canonical and canonical not in latest:
            latest[canonical] = float(row.values[col])
    return latest


def _indicator_map(table: br.ReportTable) -> dict[str, dict[str, float]]:
    """{canonical code: {period: value}} for every recognised indicator row."""
    out: dict[str, dict[str, float]] = {}
    for row in table.rows:
        canonical = fields.match_indicator(row.label, row.field_code)
        if canonical is None:
            continue
        for period, value in zip(table.periods, row.values):
            if value is not None:
                out.setdefault(canonical, {})[period] = float(value)
    return out


def _latest_per_indicator(ind: dict[str, dict[str, float]]) -> dict[str, tuple[str, float]]:
    """Replicates dossier.load_indicators_latest: newest period per code."""
    latest: dict[str, tuple[str, float]] = {}
    for code, by_period in ind.items():
        best_period = max(by_period, key=lambda p: p)  # string periods sort ok here
        latest[code] = (best_period, by_period[best_period])
    return latest


def run(ticker: str, *, force: bool) -> dict:
    profile_html = _fetch("profile", ticker, force=force)
    if profile_html is None:
        return {"ticker": ticker, "error": "profile fetch failed"}
    profile = br.parse_profile(profile_html, ticker)
    slug = profile.slug or ticker  # report pages MUST use the slug (redirect trap)

    pages: dict[str, br.ReportTable] = {}
    dividends: list[br.DividendEntry] = []
    for kind in REPORT_PAGES:
        html = _fetch(kind, slug, force=force)
        if html is None:
            continue
        if kind == "dividends":
            dividends = br.parse_dividends(html)
            continue
        freq = "Q"
        try:
            pages[kind] = br.parse_report_table(html, freq)
        except br.ParseError as exc:
            print(f"  ! {kind}: parse error — {exc}", file=sys.stderr)

    income = _income_series(pages["income_q"]) if "income_q" in pages else {}
    quarters = metrics.compute_quarter_metrics(income)[-12:]
    balance_latest = _balance_latest(pages["balance_q"]) if "balance_q" in pages else {}
    net_cash_value, net_cash_note = metrics.compute_net_cash(balance_latest)

    ind = {}
    for kind in ("indicators_value", "indicators_profitability"):
        if kind in pages:
            for code, by_period in _indicator_map(pages[kind]).items():
                ind.setdefault(code, {}).update(by_period)
    indicators_latest = _latest_per_indicator(ind)
    cz_values = list(ind.get("cz", {}).values())

    ttm = metrics.compute_ttm(
        income, profile.shares_outstanding, profile.price,
        reported_market_cap=profile.market_cap,
    )
    pe_history = metrics.compute_pe_history(cz_values, ttm.pe)

    quarters_dicts = [q.to_dict() for q in quarters]
    ttm_dict = ttm.to_dict()
    pe_history_dict = pe_history.to_dict()
    dividend_yield_latest = next(
        (float(d.yield_pct) for d in dividends if d.yield_pct is not None), None
    )
    company_insights = insights.build_insights(
        sector=profile.sector,
        quarters=quarters_dicts,
        ttm=ttm_dict,
        pe_history=pe_history_dict,
        net_cash_value=net_cash_value,
        balance_latest=balance_latest,
        indicators_latest=indicators_latest,
        dividend_years=[d.year for d in dividends],
        dividend_yield_latest=dividend_yield_latest,
        price_age_days=None,  # profile quote, not a stored dated price
    )
    prescore = metrics.compute_prescore(
        quarters=quarters, ttm=ttm, pe_history=pe_history,
        net_cash_value=net_cash_value, net_cash_note=net_cash_note,
        dividend_years=[d.year for d in dividends], forward_pe=None,
    )
    thesis_inputs = thesis.ThesisInputs(
        insights=company_insights,
        ttm=ttm_dict,
        pe_history=pe_history_dict,
        net_cash={"value": net_cash_value, "note": net_cash_note},
        latest_forecast=None,  # no DB forecast → trailing C/Z fallback (honest)
        prescore=prescore.to_dict(),
    )
    result = thesis.build_thesis(thesis_inputs, malik.MALIK).to_dict()

    return {
        "ticker": ticker,
        "slug": slug,
        "raw": {
            "profile": {
                "name": profile.name, "sector": profile.sector,
                "market": profile.market, "shares_outstanding": profile.shares_outstanding,
                "market_cap_reported_PLN": profile.market_cap,
                "enterprise_value_PLN": profile.enterprise_value,
                "price_PLN": profile.price,
            },
            "ttm": ttm_dict,
            "pe_history": {**pe_history_dict, "cz_points": len(cz_values)},
            "net_cash": {"value_tysPLN": net_cash_value, "note": net_cash_note},
            "last_quarters": quarters_dicts[-4:],
            "indicators_latest": {k: v for k, v in sorted(indicators_latest.items())},
            "dividends": [
                {"year": d.year, "dps": d.dps, "yield_pct": d.yield_pct}
                for d in dividends[:6]
            ],
            "size": {"code": company_insights.size_code, "label": company_insights.size_label},
            "sector_group": company_insights.sector_group,
            "prescore": f"{prescore.passed}/{prescore.total}",
        },
        "insights_key_indicators": [
            {"id": i.id, "verdict": i.verdict, "value": i.value, "brief": i.brief}
            for i in company_insights.key_indicators
        ],
        "insights_missing": [m.id for m in company_insights.missing],
        "thesis": result,
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    if len(args) != 1:
        print(__doc__)
        return 1
    ticker = args[0].upper()
    print(f"# validating {ticker} (force={force})", file=sys.stderr)
    out = run(ticker, force=force)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"# HTTP requests this run: {_REQUESTS['count']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
