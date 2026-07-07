"""Quarterly metrics, TTM aggregates and the deterministic prescore.

Everything here is a pure function over plain dicts/dataclasses — no DB, no
framework (unit-testable like a C# domain library). Input series come from
services/dossier.py which maps stored rows to canonical fields.

Units, once and for all:
- statement values: tys. PLN (as reported by BiznesRadar)
- price: PLN per share  |  market cap: PLN  |  EPS: PLN per share
"""
from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass

IncomeSeries = dict[str, dict[str, float]]  # period -> canonical field -> value

_PERIOD_RE = re.compile(r"^(\d{4})Q([1-4])$")

SMALL_CAP_THRESHOLD_PLN = 1_000_000_000  # < 1 mld zł ≈ the strategy's hunting ground
ONE_OFF_SHARE_LIMIT_PCT = 30.0

# Size classes for display + the dynamic-analysis layer (thresholds in PLN).
# The prescore's small-cap rule keeps using SMALL_CAP_THRESHOLD_PLN.
SIZE_CLASSES: tuple[tuple[str, str, float], ...] = (
    ("micro", "Mikro spółka", 150_000_000),
    ("small", "Mała spółka", SMALL_CAP_THRESHOLD_PLN),
    ("mid", "Średnia spółka", 5_000_000_000),
    ("large", "Duża spółka", float("inf")),
)


def classify_size(market_cap: float | None) -> tuple[str | None, str | None]:
    """Market cap (PLN) → (code, Polish label); (None, None) when unknown."""
    if market_cap is None or market_cap <= 0:
        return None, None
    for code, label, upper in SIZE_CLASSES:
        if market_cap < upper:
            return code, label
    return None, None  # pragma: no cover — inf upper bound is unreachable


def period_key(period: str) -> tuple[int, int]:
    match = _PERIOD_RE.match(period)
    if not match:
        raise ValueError(f"Not a quarterly period: {period!r}")
    return int(match.group(1)), int(match.group(2))


def sort_periods(periods) -> list[str]:
    return sorted(periods, key=period_key)


def previous_year_period(period: str) -> str:
    year, quarter = period_key(period)
    return f"{year - 1}Q{quarter}"


def next_period(period: str) -> str:
    year, quarter = period_key(period)
    return f"{year}Q{quarter + 1}" if quarter < 4 else f"{year + 1}Q1"


def _pct_change(current: float | None, previous: float | None) -> float | None:
    """Year-over-year change in %; None when either side is missing or the
    base is non-positive (a sign flip makes the ratio meaningless)."""
    if current is None or previous is None or previous <= 0:
        return None
    return round((current / previous - 1.0) * 100.0, 1)


def _ratio_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return round(numerator / denominator * 100.0, 1)


def derive_income_fields(income: IncomeSeries) -> IncomeSeries:
    """Fill gaps in statement variants (mutates and returns the series).

    Production finding (SNT, 'kalkulacyjny' layout): BiznesRadar tags its
    'Zysk ze sprzedaży' row as IncomeGrossProfit and has NO separate
    profit-on-sales row — so:
      gross_profit    = revenue − cogs                    (when absent)
      profit_on_sales = gross − selling − admin costs     (when absent)
    """
    for data in income.values():
        if "gross_profit" not in data and {"revenue", "cogs"} <= data.keys():
            data["gross_profit"] = round(data["revenue"] - data["cogs"], 1)
        if (
            "profit_on_sales" not in data
            and {"gross_profit", "selling_costs", "admin_costs"} <= data.keys()
        ):
            data["profit_on_sales"] = round(
                data["gross_profit"] - data["selling_costs"] - data["admin_costs"], 1
            )
        # Reverse derivation: some layouts report profit-on-sales + both cost
        # lines but no gross row — reconstruct it so the key margin exists.
        if (
            "gross_profit" not in data
            and {"profit_on_sales", "selling_costs", "admin_costs"} <= data.keys()
        ):
            data["gross_profit"] = round(
                data["profit_on_sales"] + data["selling_costs"] + data["admin_costs"], 1
            )
    return income


# ------------------------------------------------------------------ quarters

@dataclass
class QuarterMetrics:
    period: str
    revenue: float | None
    revenue_yoy_pct: float | None
    gross_margin_pct: float | None  # marża brutto na sprzedaży — the key metric
    sales_margin_pct: float | None  # after selling + admin costs
    net_margin_pct: float | None
    profit_on_sales: float | None
    operating_profit: float | None
    net_profit: float | None
    one_off_share_pct: float | None  # |EBIT − profit on sales| / |EBIT|

    def to_dict(self) -> dict:
        return asdict(self)


def compute_quarter_metrics(income: IncomeSeries) -> list[QuarterMetrics]:
    result: list[QuarterMetrics] = []
    for period in sort_periods(income.keys()):
        quarter = income[period]
        previous = income.get(previous_year_period(period), {})

        revenue = quarter.get("revenue")
        operating = quarter.get("operating_profit")
        on_sales = quarter.get("profit_on_sales")

        one_off_share = None
        if operating is not None and on_sales is not None and operating != 0:
            one_off_share = round(abs(operating - on_sales) / abs(operating) * 100.0, 1)

        result.append(
            QuarterMetrics(
                period=period,
                revenue=revenue,
                revenue_yoy_pct=_pct_change(revenue, previous.get("revenue")),
                gross_margin_pct=_ratio_pct(quarter.get("gross_profit"), revenue),
                sales_margin_pct=_ratio_pct(on_sales, revenue),
                net_margin_pct=_ratio_pct(quarter.get("net_profit"), revenue),
                profit_on_sales=on_sales,
                operating_profit=operating,
                net_profit=quarter.get("net_profit"),
                one_off_share_pct=one_off_share,
            )
        )
    return result


# ----------------------------------------------------------------------- TTM

@dataclass
class TtmAggregates:
    net_profit: float | None  # tys. PLN, trailing 4 quarters
    eps: float | None  # PLN
    pe: float | None
    market_cap: float | None  # PLN
    price: float | None
    # Where market_cap came from and how well the two sources agree.
    # "reported" = BiznesRadar profile figure (authoritative); "derived" =
    # price × shares (fallback). check_pct = |derived − reported| / reported,
    # in % — a large value means stale price or misparsed share count.
    market_cap_source: str | None = None
    market_cap_check_pct: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def compute_ttm(
    income: IncomeSeries,
    shares_outstanding: int | None,
    price: float | None,
    reported_market_cap: float | None = None,
) -> TtmAggregates:
    periods_with_net = [
        p for p in sort_periods(income.keys()) if income[p].get("net_profit") is not None
    ]
    ttm_net: float | None = None
    if len(periods_with_net) >= 4:
        ttm_net = round(sum(income[p]["net_profit"] for p in periods_with_net[-4:]), 1)

    derived_cap = eps = pe = None
    if shares_outstanding and price is not None:
        derived_cap = round(price * shares_outstanding, 0)
    if shares_outstanding and ttm_net is not None:
        eps = round(ttm_net * 1000.0 / shares_outstanding, 4)  # tys. PLN → PLN
    if eps is not None and eps > 0 and price is not None:
        pe = round(price / eps, 2)

    # The REPORTED market cap wins: deriving it silently understates size when
    # the stored price or the share count is stale/misparsed (production bug:
    # a company worth >1 mld PLN passed the small-cap check).
    market_cap = source = check_pct = None
    if reported_market_cap is not None and reported_market_cap > 0:
        market_cap, source = reported_market_cap, "reported"
        if derived_cap is not None:
            check_pct = round(
                abs(derived_cap - reported_market_cap) / reported_market_cap * 100.0, 1
            )
    elif derived_cap is not None:
        market_cap, source = derived_cap, "derived"

    return TtmAggregates(
        net_profit=ttm_net,
        eps=eps,
        pe=pe,
        market_cap=market_cap,
        price=price,
        market_cap_source=source,
        market_cap_check_pct=check_pct,
    )


# ------------------------------------------------------------------- P/E hist

@dataclass
class PeHistoryStats:
    median: float | None
    q1: float | None
    q3: float | None
    current: float | None
    percentile: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def compute_pe_history(history: list[float], current: float | None) -> PeHistoryStats:
    """Stats over the company's OWN historical P/E — the strategy compares a
    stock against its history, not against the market."""
    values = sorted(v for v in history if v is not None and v > 0)
    if not values:
        return PeHistoryStats(None, None, None, current, None)

    if len(values) == 1:
        q1 = median = q3 = values[0]
    else:
        q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive")

    percentile = None
    if current is not None:
        percentile = round(100.0 * sum(v <= current for v in values) / len(values), 0)

    return PeHistoryStats(
        median=round(median, 2),
        q1=round(q1, 2),
        q3=round(q3, 2),
        current=current,
        percentile=percentile,
    )


# ------------------------------------------------------------------- net cash

def compute_net_cash(balance_latest: dict[str, float]) -> tuple[float | None, str]:
    """cash − financial debt from the latest balance sheet; honest about gaps.

    Debt is the sum of every `debt_*` component present (borrowings, bonds,
    leasing × long/short — the split BiznesRadar actually reports).
    """
    cash = balance_latest.get("cash")
    if cash is None:
        return None, "Brak pozycji gotówki w danych bilansowych."
    debt_components = {
        key: value for key, value in balance_latest.items()
        if key.startswith("debt_") and value is not None
    }
    if not debt_components:
        return round(cash, 1), "Gotówka bez pozycji długu w danych — przyjęto dług 0."
    debt = sum(debt_components.values())
    return (
        round(cash - debt, 1),
        f"Gotówka minus dług finansowy (kredyty/obligacje/leasing, "
        f"{len(debt_components)} pozycji).",
    )


# ------------------------------------------------------------------- prescore

@dataclass
class CheckResult:
    id: str
    name: str  # user-facing, Polish
    verdict: str  # pass | fail | unknown
    evidence: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Prescore:
    passed: int
    total: int
    checks: list[CheckResult]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total": self.total,
            "checks": [c.to_dict() for c in self.checks],
        }


def _fmt(value: float | None, suffix: str = "") -> str:
    return "b/d" if value is None else f"{value:g}{suffix}"


def compute_prescore(
    quarters: list[QuarterMetrics],
    ttm: TtmAggregates,
    pe_history: PeHistoryStats,
    net_cash_value: float | None,
    net_cash_note: str,
    dividend_years: list[int],
    forward_pe: float | None = None,
) -> Prescore:
    """The 8 deterministic checklist rules from PLAN §7.

    'unknown' is an honest verdict, never silently converted to pass/fail —
    the AI layer (and you) see exactly which data was missing.
    """
    checks: list[CheckResult] = []

    def add(check_id: str, name: str, verdict: str, evidence: str) -> None:
        checks.append(CheckResult(check_id, name, verdict, evidence))

    # 1. Revenue growing y/y in the last two quarters.
    recent_yoy = [q.revenue_yoy_pct for q in quarters[-2:]]
    if len(recent_yoy) < 2 or any(v is None for v in recent_yoy):
        add("revenue_growth", "Wzrost przychodów r/r", "unknown", "Za mało danych o przychodach.")
    else:
        verdict = "pass" if all(v > 0 for v in recent_yoy) else "fail"
        add(
            "revenue_growth", "Wzrost przychodów r/r", verdict,
            f"Ostatnie 2 kw.: {recent_yoy[0]:+.1f}% i {recent_yoy[1]:+.1f}%.",
        )

    # 2. Gross sales margin: last 2 quarters vs the 4 before them.
    margins = [q.gross_margin_pct for q in quarters if q.gross_margin_pct is not None]
    if len(margins) < 6:
        add("gross_margin_trend", "Trend marży brutto na sprzedaży", "unknown",
            "Potrzeba min. 6 kwartałów z marżą.")
    else:
        recent = sum(margins[-2:]) / 2
        base = sum(margins[-6:-2]) / 4
        verdict = "pass" if recent > base else "fail"
        add("gross_margin_trend", "Trend marży brutto na sprzedaży", verdict,
            f"Śr. 2 ost. kw. {recent:.1f}% vs {base:.1f}% w 4 wcześniejszych.")

    # 3. Operating leverage: profit on sales growing faster than revenue.
    latest = quarters[-1] if quarters else None
    prev_year = None
    if latest is not None:
        for q in quarters:
            if q.period == previous_year_period(latest.period):
                prev_year = q
                break
    if (
        latest is None or prev_year is None
        or latest.profit_on_sales is None or prev_year.profit_on_sales is None
        or latest.revenue_yoy_pct is None or prev_year.profit_on_sales <= 0
    ):
        add("operating_leverage", "Dźwignia operacyjna", "unknown",
            "Brak porównywalnych danych r/r.")
    else:
        profit_yoy = (latest.profit_on_sales / prev_year.profit_on_sales - 1) * 100
        verdict = "pass" if profit_yoy > latest.revenue_yoy_pct else "fail"
        add("operating_leverage", "Dźwignia operacyjna", verdict,
            f"Zysk ze sprzedaży {profit_yoy:+.1f}% vs przychody "
            f"{latest.revenue_yoy_pct:+.1f}% r/r.")

    # 4. Profit quality: one-offs small relative to operating profit.
    if latest is None or latest.one_off_share_pct is None:
        add("profit_quality", "Jakość zysku (one-offy)", "unknown",
            "Brak danych o pozostałej działalności operacyjnej.")
    else:
        verdict = "pass" if latest.one_off_share_pct < ONE_OFF_SHARE_LIMIT_PCT else "fail"
        add("profit_quality", "Jakość zysku (one-offy)", verdict,
            f"Pozostała działalność = {latest.one_off_share_pct:.1f}% zysku operacyjnego "
            f"(limit {ONE_OFF_SHARE_LIMIT_PCT:.0f}%).")

    # 5. P/E vs the company's own history (forward P/E preferred when available).
    current_pe = forward_pe if forward_pe is not None else ttm.pe
    pe_label = "C/Z prognozowane" if forward_pe is not None else "C/Z TTM"
    if current_pe is None or pe_history.median is None:
        add("pe_vs_history", "C/Z vs własna historia", "unknown",
            f"{pe_label}: {_fmt(current_pe)}, mediana hist.: {_fmt(pe_history.median)}.")
    else:
        verdict = "pass" if current_pe < pe_history.median else "fail"
        add("pe_vs_history", "C/Z vs własna historia", verdict,
            f"{pe_label} {current_pe:.1f} vs mediana {pe_history.median:.1f}.")

    # 6. Net cash.
    if net_cash_value is None:
        add("net_cash", "Gotówka netto", "unknown", net_cash_note)
    else:
        verdict = "pass" if net_cash_value > 0 else "fail"
        add("net_cash", "Gotówka netto", verdict,
            f"{net_cash_value:,.0f} tys. zł. {net_cash_note}".replace(",", " "))

    # 7. Small cap — the strategy's edge lives below institutional radar.
    if ttm.market_cap is None:
        add("small_cap", "Mała spółka", "unknown",
            "Brak kapitalizacji (ani raportowanej, ani kursu × liczby akcji).")
    else:
        verdict = "pass" if ttm.market_cap < SMALL_CAP_THRESHOLD_PLN else "fail"
        _, size_label = classify_size(ttm.market_cap)
        source_note = (
            "wg BiznesRadar" if ttm.market_cap_source == "reported"
            else "kurs × liczba akcji"
        )
        add("small_cap", "Mała spółka", verdict,
            f"Kapitalizacja {ttm.market_cap / 1e6:,.0f} mln zł ({source_note}) "
            f"— {size_label or 'b/d'}; próg "
            f"{SMALL_CAP_THRESHOLD_PLN / 1e9:.0f} mld.".replace(",", " "))

    # 8. Dividend as a bonus signal of capital discipline.
    if not dividend_years:
        add("dividend", "Dywidenda (bonus)", "unknown",
            "Brak danych o dywidendach (spółka mogła nigdy nie płacić).")
    else:
        latest_year = max(
            (period_key(q.period)[0] for q in quarters), default=max(dividend_years)
        )
        recent = [y for y in dividend_years if y >= latest_year - 2]
        verdict = "pass" if recent else "fail"
        add("dividend", "Dywidenda (bonus)", verdict,
            f"Wypłaty w latach: {', '.join(map(str, sorted(dividend_years)[-5:]))}.")

    passed = sum(1 for c in checks if c.verdict == "pass")
    return Prescore(passed=passed, total=len(checks), checks=checks)
