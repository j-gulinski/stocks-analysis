"""Reproducible engine-output dump for the scenario/thesis PREVIEWS (Part B).

WHY this exists (not a product module — a preview helper, kept next to the
previews it feeds): the visual previews in this folder must show REAL
deterministic engine output, never hand-typed numbers. This script rebuilds the
*pure* half of `dossier.build_dossier` (exactly as `scripts/validate_thesis.py`
does — parsers -> fields -> metrics -> insights -> thesis) from the committed
DECORA (DEC) fixtures, then additionally runs the scenario engine
(`scenarios.build_scenario_set` + `scenarios_ai.simulate_scenarios`) and the
potential-valuation agent (`valuation_ai.assess_potential`) on the no-API-key
deterministic path, and writes the whole thing to JSON.

The sandbox has no Postgres/SQLAlchemy/pydantic, so `dossier.build_dossier`
itself cannot run here; every engine it calls IS pure, so we call them directly
with hand-assembled inputs — the same technique the validation harness uses.

Price source (the one place we diverge from validate_thesis.py, on purpose):
`dossier.py` reads the current price from stored Price rows (populated by the
stooq / archiwum scrapers), NOT from the profile quote. The committed synthetic
DECORA profile carries no quote, so validate_thesis.py leaves price None. To
render the panel as the REAL app would (a live weighted potential, a
bieżący -> oczekiwany price line), we source the price the same way production
does: the latest close from the committed stooq fixture
(tests/fixtures/stooq_daily.csv). For DECORA that close (24.50) equals the
fixture's reported market cap / shares exactly — internally consistent, no
invented number.

Run (from repo root, bare system python is enough):
    python3 docs/previews/_render_engine_output.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
FIXTURES = BACKEND / "tests" / "fixtures"
OUT_DIR = REPO / "docs" / "previews"

sys.path.insert(0, str(BACKEND))

from app.scrapers import biznesradar as br  # noqa: E402
from app.scrapers import stooq  # noqa: E402
from app.services import (  # noqa: E402
    fields,
    insights,
    metrics,
    scenarios,
    scenarios_ai,
    thesis,
    thesis_ai,
    valuation_ai,
)
from app.services.strategies import malik  # noqa: E402

# No key -> every AI refiner takes its deterministic pass-through path.
NO_KEY = SimpleNamespace(anthropic_api_key=None)


def _income_series(table: br.ReportTable) -> metrics.IncomeSeries:
    """Mirror dossier.load_income_series: highest-ranked row wins per
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
    latest: dict[str, tuple[str, float]] = {}
    for code, by_period in ind.items():
        best_period = max(by_period, key=lambda p: p)
        latest[code] = (best_period, by_period[best_period])
    return latest


def build(ticker: str) -> dict:
    profile = br.parse_profile((FIXTURES / "br_profile.html").read_text(), ticker)

    income = _income_series(
        br.parse_report_table((FIXTURES / "br_income_q.html").read_text(), "Q")
    )
    quarters = metrics.compute_quarter_metrics(income)[-12:]

    balance_latest = _balance_latest(
        br.parse_report_table((FIXTURES / "br_balance_q.html").read_text(), "Q")
    )
    net_cash_value, net_cash_note = metrics.compute_net_cash(balance_latest)

    ind: dict[str, dict[str, float]] = {}
    for name in ("br_indicators_value.html", "br_indicators_profitability.html"):
        table = br.parse_report_table((FIXTURES / name).read_text(), "Q")
        for code, by_period in _indicator_map(table).items():
            ind.setdefault(code, {}).update(by_period)
    indicators_latest = _latest_per_indicator(ind)
    cz_values = list(ind.get("cz", {}).values())

    dividends = br.parse_dividends((FIXTURES / "br_dividend.html").read_text())

    # PRICE — sourced the way dossier.py sources it (stored Price rows), here the
    # committed stooq fixture's latest close (see module docstring).
    bars = stooq.parse_prices_csv((FIXTURES / "stooq_daily.csv").read_text())
    latest_bar = max(bars, key=lambda b: b.day)
    price = latest_bar.close
    price_date = latest_bar.day

    ttm = metrics.compute_ttm(
        income, profile.shares_outstanding, price, reported_market_cap=profile.market_cap
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
        price_age_days=None,
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
        latest_forecast=None,  # no DB forecast -> trailing C/Z basis (honest)
        prescore=prescore.to_dict(),
    )
    company_thesis = thesis.build_thesis(thesis_inputs, malik.MALIK)
    thesis_block = thesis_ai.refine_thesis(
        thesis_inputs, malik.MALIK, company_thesis, ticker=ticker, settings=NO_KEY
    )

    # --- scenarios (mirror dossier.py wiring for the sector-selected multiple) --
    selected_multiple = scenarios.select_valuation_multiple(
        company_insights.sector_group, malik.MALIK
    )
    if selected_multiple == "cz":
        multiple_series, multiple_current = cz_values, ttm.pe
    else:
        multiple_series = list(ind.get(selected_multiple, {}).values())
        latest_entry = indicators_latest.get(selected_multiple)
        multiple_current = latest_entry[1] if latest_entry else None
    multiple_history = metrics.compute_multiple_history(multiple_series, multiple_current)

    scenario_inputs = scenarios.ScenarioInputs(
        thesis_inputs=thesis_inputs,
        multiple_history=multiple_history.to_dict(),
        eps=ttm.eps,
        book_value=balance_latest.get("equity"),
        ebitda_ttm=None,  # not computed anywhere yet -> energy falls back to C/Z
        shares_outstanding=profile.shares_outstanding,
        current_price=ttm.price,
        net_cash=net_cash_value,
    )
    scenario_set = scenarios.build_scenario_set(scenario_inputs, malik.MALIK)
    scenarios_block = scenarios_ai.simulate_scenarios(
        scenario_inputs, malik.MALIK, scenario_set, ticker=ticker, settings=NO_KEY
    )
    valuation_block = valuation_ai.assess_potential(
        scenario_inputs, scenarios_block, malik.MALIK, ticker=ticker, settings=NO_KEY
    )

    return {
        "_meta": {
            "ticker": ticker,
            "source": "committed synthetic DECORA fixtures (backend/tests/fixtures/"
            "br_*.html) + stooq_daily.csv for price; identical to "
            "backend/.cache/validation/DEC_*.html",
            "price_source": f"stooq_daily.csv latest close {price} on {price_date} "
            "(== reported market cap / shares)",
            "engine_entry_points": [
                "thesis.build_thesis + thesis_ai.refine_thesis (no key -> deterministic)",
                "scenarios.build_scenario_set + scenarios_ai.simulate_scenarios "
                "(no key -> deterministic)",
                "valuation_ai.assess_potential (no key -> deterministic)",
            ],
            "strategy": {"id": malik.MALIK.id, "label": malik.MALIK.label},
        },
        "company": {
            "ticker": ticker,
            "name": profile.name,
            "market": profile.market,
            "sector": profile.sector,
            "shares_outstanding": profile.shares_outstanding,
        },
        "ttm": {**ttm_dict, "price_date": str(price_date)},
        "pe_history": pe_history_dict,
        "multiple_history": multiple_history.to_dict(),
        "net_cash": {"value": net_cash_value, "note": net_cash_note},
        "insights": company_insights.to_dict(),
        "prescore": prescore.to_dict(),
        "thesis": thesis_block,
        "scenarios": scenarios_block,
        "valuation": valuation_block,
    }


def main() -> int:
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "DEC"
    out = build(ticker)
    dest = OUT_DIR / f"dossier-{ticker}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    # Console summary for a quick human sanity-check.
    sc = out["scenarios"]
    val = out["valuation"]
    print(f"# {ticker} — engine output written to {dest.relative_to(REPO)}")
    print(f"  thesis.entry_quality : {out['thesis']['entry_quality']['code']} "
          f"({out['thesis']['entry_quality']['label']}) | engine={out['thesis']['engine']}")
    print(f"  ttm.price / pe / eps : {out['ttm']['price']} / {out['ttm']['pe']} / {out['ttm']['eps']}")
    print(f"  scenarios.multiple   : {sc['valuation_multiple']} | engine={sc['engine']}")
    print(f"  weighted EV / upside : {sc['weighted_expected_price']} zl "
          f"/ {sc['weighted_expected_upside_pct']}%")
    for s in sc["scenarios"]:
        print(f"    - {s['kind']:8} p={s['probability']} target={s['target_price']} "
              f"upside={s['implied_upside_pct']}%")
    print(f"  valuation.potential  : {val['potential']['value_pct']}% "
          f"(range {val['potential']['range_pct']}) | conf={val['confidence']['level']} "
          f"| engine={val['engine']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
