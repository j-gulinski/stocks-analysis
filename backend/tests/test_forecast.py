"""Forecast engine tests: defaults derivation + hand-checked computation,
including the shape of the Novita example from the source transcript."""
import pytest

from app.services import forecast as fc
from tests.test_metrics import DATA, KEYS, PRICE, SHARES


@pytest.fixture()
def income():
    return {p: dict(zip(KEYS, row)) for p, row in DATA.items()}


def test_default_assumptions_mirror_the_excel_workflow(income):
    defaults = fc.default_assumptions(income)

    assert defaults.period == "2025Q2"  # next quarter after the last known one
    assert defaults.revenue == 62700  # last quarter's revenue
    assert defaults.gross_margin_pct == 34.0  # last quarter's margin
    assert defaults.selling_costs_pct == 12.0  # avg of last 4 quarters
    assert defaults.admin_costs == 3900  # last quarter (watch Q4 reserves)
    assert defaults.other_operating == 49.0  # avg(10, 23, 57, 106)
    assert defaults.financial_net == -150.0  # avg(−160, −140, −130, −170)
    assert defaults.tax_rate == 0.19
    assert defaults.depreciation == 2000


def test_default_assumptions_require_history():
    with pytest.raises(ValueError):
        fc.default_assumptions({})


def test_compute_forecast_hand_checked(income):
    assumptions = fc.ForecastAssumptions(
        period="2025Q2", revenue=64000, gross_margin_pct=33.5,
        selling_costs_pct=12.0, admin_costs=3900, other_operating=49.0,
        financial_net=-150.0, depreciation=2000,
    )
    result = fc.compute_forecast(assumptions, income, SHARES, PRICE)

    pnl = result["pnl"]
    assert pnl["gross_profit"] == 21440.0  # 64000 × 33.5%
    assert pnl["selling_costs"] == 7680.0  # 64000 × 12%
    assert pnl["profit_on_sales"] == 9860.0  # 21440 − 7680 − 3900
    assert pnl["operating_profit"] == 9909.0
    assert pnl["pretax_profit"] == 9759.0
    assert pnl["tax"] == 1854.2  # 19% CIT
    assert pnl["net_profit"] == 7904.8
    assert pnl["ebitda"] == 11909.0

    yoy = result["yoy"]
    assert yoy["period"] == "2024Q2"
    assert yoy["net_profit"] == 6107
    assert yoy["net_profit_change_pct"] == 29.4
    assert yoy["revenue_change_pct"] == 11.9

    forward = result["forward"]
    assert forward["ttm_net_profit"] == 28689.8  # 6691 + 6132 + 7962 + forecast
    assert forward["eps"] == 2.7152
    assert forward["pe"] == 9.02  # vs own median 11.35 → the buy signal shape


def test_forecast_loss_has_no_tax(income):
    assumptions = fc.ForecastAssumptions(
        period="2025Q2", revenue=10000, gross_margin_pct=10.0,
        selling_costs_pct=12.0, admin_costs=3900,
    )
    result = fc.compute_forecast(assumptions, income)
    assert result["pnl"]["pretax_profit"] < 0
    assert result["pnl"]["tax"] == 0.0
    assert result["forward"]["pe"] is None or result["forward"]["pe"] > 0


def test_transcript_novita_shape():
    """The video's quick forecast: pretax ≈ 13.0M → net ≈ 10.53M, EBITDA ≈ 14.6M."""
    assumptions = fc.ForecastAssumptions(
        period="2020Q4", revenue=51800, gross_margin_pct=40.0,
        selling_costs_pct=10.0, admin_costs=2590, other_operating=50.0,
        depreciation=1600,
    )
    result = fc.compute_forecast(assumptions, {})
    assert result["pnl"]["pretax_profit"] == 13000.0
    assert result["pnl"]["tax"] == 2470.0
    assert result["pnl"]["net_profit"] == 10530.0
    assert result["pnl"]["ebitda"] == 14600.0
    # no history → honest Nones, no fake comparisons
    assert result["yoy"]["net_profit"] is None
    assert result["forward"]["ttm_net_profit"] is None
