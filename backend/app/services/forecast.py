"""Next-quarter forecast engine — the Excel workflow from the transcript,
as a pure function.

The workflow being replicated (docs/source-materials, BiznesRadar→Excel video):
assume revenue and gross margin, take selling costs as a % of revenue, admin
costs from the last quarter (watch Q4 bonus reserves), average the noisy small
lines over 4 quarters, apply 19% CIT → net profit → forward P/E vs the
company's own history.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.services.metrics import IncomeSeries, next_period, previous_year_period, sort_periods

DEFAULT_TAX_RATE = 0.19  # Polish CIT


@dataclass
class ForecastAssumptions:
    period: str  # the quarter being forecast, e.g. 2025Q2
    revenue: float  # tys. PLN
    gross_margin_pct: float
    selling_costs_pct: float  # % of revenue
    admin_costs: float  # tys. PLN
    other_operating: float = 0.0  # net effect, tys. PLN
    financial_net: float = 0.0  # net financial income − costs, tys. PLN
    tax_rate: float = DEFAULT_TAX_RATE
    depreciation: float | None = None  # for EBITDA

    def to_dict(self) -> dict:
        return asdict(self)


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def default_assumptions(income: IncomeSeries) -> ForecastAssumptions:
    """Prefill from history exactly like the transcript does (all overridable).

    Raises ValueError when there is no usable revenue history — callers turn
    that into a 409/422, not a crash.
    """
    periods = [p for p in sort_periods(income.keys()) if income[p].get("revenue")]
    if not periods:
        raise ValueError("No revenue history — refresh financials first.")
    last = income[periods[-1]]
    last_revenue = last["revenue"]

    gross_margin_pct = 0.0
    if last.get("gross_profit") is not None:
        gross_margin_pct = round(last["gross_profit"] / last_revenue * 100.0, 1)

    selling_ratios = [
        income[p]["selling_costs"] / income[p]["revenue"] * 100.0
        for p in periods[-4:]
        if income[p].get("selling_costs") is not None and income[p].get("revenue")
    ]
    other_values = [
        income[p]["operating_profit"] - income[p]["profit_on_sales"]
        for p in periods[-4:]
        if income[p].get("operating_profit") is not None
        and income[p].get("profit_on_sales") is not None
    ]
    financial_values = [
        income[p]["pretax_profit"] - income[p]["operating_profit"]
        for p in periods[-4:]
        if income[p].get("pretax_profit") is not None
        and income[p].get("operating_profit") is not None
    ]

    return ForecastAssumptions(
        period=next_period(periods[-1]),
        revenue=last_revenue,
        gross_margin_pct=gross_margin_pct,
        selling_costs_pct=round(_avg(selling_ratios) or 0.0, 1),
        admin_costs=last.get("admin_costs") or 0.0,
        other_operating=_avg(other_values) or 0.0,
        financial_net=_avg(financial_values) or 0.0,
        tax_rate=DEFAULT_TAX_RATE,
        depreciation=last.get("depreciation"),
    )


def compute_forecast(
    assumptions: ForecastAssumptions,
    income: IncomeSeries,
    shares_outstanding: int | None = None,
    price: float | None = None,
) -> dict:
    """Full forecast P&L + y/y comparison + forward P/E. Pure math, no I/O."""
    a = assumptions
    gross_profit = round(a.revenue * a.gross_margin_pct / 100.0, 1)
    selling_costs = round(a.revenue * a.selling_costs_pct / 100.0, 1)
    profit_on_sales = round(gross_profit - selling_costs - a.admin_costs, 1)
    operating_profit = round(profit_on_sales + a.other_operating, 1)
    pretax_profit = round(operating_profit + a.financial_net, 1)
    # Simplification: no tax shield on a forecast loss (deferred tax assets are
    # exactly the kind of detail to verify in the actual report).
    tax = round(pretax_profit * a.tax_rate, 1) if pretax_profit > 0 else 0.0
    net_profit = round(pretax_profit - tax, 1)
    ebitda = (
        round(operating_profit + a.depreciation, 1) if a.depreciation is not None else None
    )

    result: dict = {
        "period": a.period,
        "pnl": {
            "revenue": a.revenue,
            "gross_profit": gross_profit,
            "selling_costs": selling_costs,
            "admin_costs": a.admin_costs,
            "profit_on_sales": profit_on_sales,
            "other_operating": a.other_operating,
            "operating_profit": operating_profit,
            "financial_net": a.financial_net,
            "pretax_profit": pretax_profit,
            "tax": tax,
            "net_profit": net_profit,
            "ebitda": ebitda,
        },
    }

    # Same quarter a year earlier — the comparison the strategy cares about.
    year_ago = income.get(previous_year_period(a.period), {})
    comparison: dict = {"period": previous_year_period(a.period)}
    for key, forecast_value in (("revenue", a.revenue), ("net_profit", net_profit)):
        base = year_ago.get(key)
        comparison[key] = base
        comparison[f"{key}_change_pct"] = (
            round((forecast_value / base - 1.0) * 100.0, 1) if base and base > 0 else None
        )
    result["yoy"] = comparison

    # Forward TTM: the forecast quarter + the three most recent actual quarters
    # strictly before it.
    known = [
        p for p in sort_periods(income.keys())
        if income[p].get("net_profit") is not None and p < a.period
    ]
    forward: dict = {"ttm_net_profit": None, "eps": None, "pe": None}
    if len(known) >= 3:
        ttm_net = round(
            sum(income[p]["net_profit"] for p in known[-3:]) + net_profit, 1
        )
        forward["ttm_net_profit"] = ttm_net
        if shares_outstanding:
            eps = round(ttm_net * 1000.0 / shares_outstanding, 4)
            forward["eps"] = eps
            if price is not None and eps > 0:
                forward["pe"] = round(price / eps, 2)
    result["forward"] = forward

    return result
