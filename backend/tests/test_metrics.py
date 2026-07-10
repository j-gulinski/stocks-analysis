"""Metrics + prescore unit tests with hand-checked numbers.

The income series mirrors tests/fixtures/br_income_q.html so unit tests and
the end-to-end API tests agree on expectations.
"""
import pytest

from app.services import metrics as m

# period: (rev, gp, sell, adm, pos, op, pretax, net, dep) — tys. PLN
DATA = {
    "2023Q1": (50000, 15000, 6000, 3500, 5500, 5500, 5300, 4293, 1800),
    "2023Q2": (52000, 15860, 6240, 3550, 6070, 6100, 5920, 4795, 1800),
    "2023Q3": (54000, 16740, 6480, 3600, 6660, 6600, 6450, 5224, 1850),
    "2023Q4": (53000, 16430, 6360, 4400, 5670, 5700, 5580, 4520, 1850),
    "2024Q1": (55000, 17325, 6600, 3700, 7025, 7000, 6820, 5524, 1900),
    "2024Q2": (57200, 18304, 6864, 3750, 7690, 7700, 7540, 6107, 1900),
    "2024Q3": (59400, 19305, 7128, 3800, 8377, 8400, 8260, 6691, 1950),
    "2024Q4": (58300, 19239, 6996, 4600, 7643, 7700, 7570, 6132, 1950),
    "2025Q1": (62700, 21318, 7524, 3900, 9894, 10000, 9830, 7962, 2000),
}
KEYS = (
    "revenue", "gross_profit", "selling_costs", "admin_costs",
    "profit_on_sales", "operating_profit", "pretax_profit", "net_profit",
    "depreciation",
)

SHARES = 10_566_435
PRICE = 24.50
CZ_HISTORY = [12.5, 11.8, 12.0, 11.5, 10.9, 11.2, 10.4, 9.8]


@pytest.fixture()
def income() -> m.IncomeSeries:
    return {p: dict(zip(KEYS, row)) for p, row in DATA.items()}


def test_period_helpers():
    assert m.period_key("2025Q1") == (2025, 1)
    assert m.previous_year_period("2025Q1") == "2024Q1"
    assert m.next_period("2024Q4") == "2025Q1"
    assert m.next_period("2025Q1") == "2025Q2"
    assert m.sort_periods(["2025Q1", "2023Q4", "2024Q2"]) == ["2023Q4", "2024Q2", "2025Q1"]
    with pytest.raises(ValueError):
        m.period_key("2024")  # annual periods never enter quarterly math


def test_quarter_metrics(income):
    by_period = {q.period: q for q in m.compute_quarter_metrics(income)}

    assert by_period["2025Q1"].revenue_yoy_pct == 14.0
    assert by_period["2024Q4"].revenue_yoy_pct == 10.0
    assert by_period["2023Q1"].revenue_yoy_pct is None  # no prior-year data

    assert by_period["2023Q1"].gross_margin_pct == 30.0
    assert by_period["2025Q1"].gross_margin_pct == 34.0
    assert by_period["2025Q1"].net_margin_pct == 12.7
    assert by_period["2025Q1"].one_off_share_pct == 1.1  # |10000−9894|/10000


def test_quarter_metrics_flags_discontinued_result_as_one_off():
    income = {
        "2026Q2": {
            "revenue": 213_185.0,
            "profit_on_sales": 53_653.0,
            "operating_profit": 53_718.0,
            "extraordinary_profit": 0.0,
            "discontinued_profit": 256_562.0,
            "net_profit": 296_362.0,
        }
    }

    quarter = m.compute_quarter_metrics(income)[0]

    assert quarter.one_off_share_pct == 477.7
    assert quarter.discontinued_profit == 256_562.0
    assert quarter.continuing_net_profit == 39_800.0
    assert quarter.discontinued_share_of_net_pct == 86.6
    assert m.compute_one_off_share(
        {
            "net_profit": 10_000.0,
            "extraordinary_profit": 0.0,
            "discontinued_profit": 0.0,
        }
    ) is None


def test_ttm(income):
    ttm = m.compute_ttm(income, SHARES, PRICE)
    assert ttm.net_profit == 26892.0  # 6107+6691+6132+7962
    assert ttm.eps == 2.545  # tys. PLN → PLN per share
    assert ttm.pe == 9.63
    assert ttm.continuing_net_profit is None
    assert ttm.valuation_pe == 9.63
    assert ttm.valuation_basis == "reported"
    assert ttm.market_cap == 258_877_658.0

    # negative TTM → no P/E instead of a nonsense negative multiple
    losses = {p: {"net_profit": -1000.0} for p in DATA}
    assert m.compute_ttm(losses, SHARES, PRICE).pe is None

    assert m.compute_ttm({}, None, None).net_profit is None


def test_ttm_uses_complete_discontinued_bridge_for_valuation():
    income = {
        "2025Q3": {"net_profit": 40_000.0, "discontinued_profit": -6_829.0},
        "2025Q4": {"net_profit": 45_000.0, "discontinued_profit": -8_658.0},
        "2026Q1": {"net_profit": 5_000.0, "discontinued_profit": -8_100.0},
        "2026Q2": {"net_profit": 296_362.0, "discontinued_profit": 256_562.0},
    }
    ttm = m.compute_ttm(income, shares_outstanding=8_529_120, price=381.6)

    assert ttm.net_profit == 386_362.0
    assert ttm.discontinued_profit == 232_975.0
    assert ttm.continuing_net_profit == 153_387.0
    assert ttm.continuing_eps == pytest.approx(17.984, abs=0.001)
    assert ttm.continuing_pe == pytest.approx(21.22, abs=0.01)
    assert ttm.valuation_eps == ttm.continuing_eps
    assert ttm.valuation_pe == ttm.continuing_pe
    assert ttm.valuation_basis == "continuing"


def test_ttm_does_not_invent_missing_discontinued_rows():
    income = {
        "2025Q3": {"net_profit": 40_000.0, "discontinued_profit": 0.0},
        "2025Q4": {"net_profit": 45_000.0},  # missing is not an explicit zero
        "2026Q1": {"net_profit": 5_000.0, "discontinued_profit": 0.0},
        "2026Q2": {"net_profit": 296_362.0, "discontinued_profit": 256_562.0},
    }
    ttm = m.compute_ttm(income, shares_outstanding=8_529_120, price=381.6)

    assert ttm.continuing_net_profit is None
    assert ttm.continuing_eps is None
    assert ttm.valuation_basis == "reported"
    assert ttm.valuation_pe == ttm.pe


def test_pe_history():
    stats = m.compute_pe_history(CZ_HISTORY, current=9.63)
    assert stats.median == 11.35
    assert stats.q1 < stats.median < stats.q3
    assert stats.percentile == 0.0  # cheaper than every point in own history

    empty = m.compute_pe_history([], current=None)
    assert empty.median is None and empty.percentile is None
    # negative P/E readings (loss periods) are excluded from the distribution
    assert m.compute_pe_history([-5.0, 10.0], current=10.0).median == 10.0


def test_net_cash():
    value, note = m.compute_net_cash(
        {"cash": 30000.0, "debt_borrowings_long": 5000.0, "debt_borrowings_short": 3000.0}
    )
    assert value == 22000.0 and "minus" in note

    assert m.compute_net_cash({})[0] is None

    partial_value, partial_note = m.compute_net_cash({"cash": 1000.0})
    assert partial_value == 1000.0 and "dług 0" in partial_note

    # full SNT-shaped debt structure: borrowings + bonds + leasing, both terms
    full, full_note = m.compute_net_cash(
        {
            "cash": 36138.0,
            "debt_borrowings_long": 2000.0,
            "debt_bonds_long": 1000.0,
            "debt_leasing_long": 1500.0,
            "debt_borrowings_short": 800.0,
            "debt_bonds_short": 0.0,
            "debt_leasing_short": 700.0,
        }
    )
    assert full == 30138.0
    assert "6 pozycji" in full_note


def test_prescore_all_pass(income):
    quarters = m.compute_quarter_metrics(income)
    ttm = m.compute_ttm(income, SHARES, PRICE)
    pe_history = m.compute_pe_history(CZ_HISTORY, ttm.pe)

    prescore = m.compute_prescore(
        quarters, ttm, pe_history,
        net_cash_value=22000.0, net_cash_note="test",
        dividend_years=[2023, 2024, 2025],
    )
    assert (prescore.passed, prescore.total) == (8, 8)
    assert all(c.verdict == "pass" for c in prescore.checks)
    assert all(c.evidence for c in prescore.checks)  # every verdict shows numbers


def test_prescore_unknowns_are_honest(income):
    quarters = m.compute_quarter_metrics(income)
    ttm = m.compute_ttm(income, None, None)  # no shares, no price
    prescore = m.compute_prescore(
        quarters, ttm, m.compute_pe_history([], None),
        net_cash_value=None, net_cash_note="no balance data",
        dividend_years=[],
    )
    verdicts = {c.id: c.verdict for c in prescore.checks}
    assert verdicts["pe_vs_history"] == "unknown"
    assert verdicts["net_cash"] == "unknown"
    assert verdicts["small_cap"] == "unknown"
    assert verdicts["dividend"] == "unknown"


def test_derive_income_fields_kalkulacyjny_layout():
    """SNT production case: no gross-profit row (BR tags 'Zysk ze sprzedaży'
    as IncomeGrossProfit) and no profit-on-sales row — both derived."""
    series = {
        "2025Q1": {
            "revenue": 100_000.0,
            "cogs": 76_000.0,
            "selling_costs": 8_000.0,
            "admin_costs": 6_000.0,
        },
        "2025Q2": {"revenue": 50_000.0},  # not enough data → nothing invented
    }
    derived = m.derive_income_fields(series)
    assert derived["2025Q1"]["gross_profit"] == 24_000.0  # revenue − cogs
    assert derived["2025Q1"]["profit_on_sales"] == 10_000.0  # gross − SG&A
    assert "gross_profit" not in derived["2025Q2"]

    # explicit rows are never overwritten
    explicit = {"2025Q1": {"revenue": 100.0, "cogs": 60.0, "gross_profit": 45.0}}
    assert m.derive_income_fields(explicit)["2025Q1"]["gross_profit"] == 45.0


def test_prescore_prefers_forward_pe(income):
    quarters = m.compute_quarter_metrics(income)
    ttm = m.compute_ttm(income, SHARES, PRICE)
    pe_history = m.compute_pe_history(CZ_HISTORY, ttm.pe)
    prescore = m.compute_prescore(
        quarters, ttm, pe_history, 22000.0, "x", [2025], forward_pe=9.02
    )
    pe_check = next(c for c in prescore.checks if c.id == "pe_vs_history")
    assert "prognozowane" in pe_check.evidence
    assert pe_check.verdict == "pass"


def test_prescore_evidence_uses_pl_decimal_comma(income):
    """Displayed checklist evidence must use the pl-PL decimal comma, never a dot
    — otherwise it drifts from the insights layer ('+1.8%' vs '+1,8%')."""
    quarters = m.compute_quarter_metrics(income)
    ttm = m.compute_ttm(income, SHARES, PRICE)
    prescore = m.compute_prescore(
        quarters, ttm, m.compute_pe_history(CZ_HISTORY, ttm.pe),
        22000.0, "x", [2025],
    )
    ev = {c.id: c.evidence for c in prescore.checks}
    # last two revenue-growth quarters (yoy 10.0 / 14.0) → decimal comma, no dot
    assert ev["revenue_growth"] == "Ostatnie 2 kw.: +10,0% i +14,0%."
    # a plain percentage (one-off share 1.1%) is comma-formatted too
    assert "1,1%" in ev["profit_quality"] and "1.1" not in ev["profit_quality"]


# ------------------------------------------------- size + reported market cap

@pytest.mark.parametrize(
    ("mcap", "expected"),
    [
        (149_999_999, "micro"),
        (999_999_999, "small"),
        (1_000_000_000, "mid"),  # the small-cap prescore threshold is exclusive
        (4_999_999_999, "mid"),
        (5_000_000_000, "large"),
        (None, None),
        (0, None),
    ],
)
def test_classify_size_boundaries(mcap, expected):
    code, label = m.classify_size(mcap)
    assert code == expected
    assert (label is None) == (expected is None)


def test_ttm_prefers_reported_market_cap(income):
    ttm = m.compute_ttm(income, SHARES, PRICE, reported_market_cap=258_877_658.0)
    assert ttm.market_cap == 258_877_658.0
    assert ttm.market_cap_source == "reported"
    # derived (24.50 × 10 566 435 ≈ same figure) agrees within rounding
    assert ttm.market_cap_check_pct is not None and ttm.market_cap_check_pct < 0.1


def test_ttm_derived_fallback_when_no_reported(income):
    ttm = m.compute_ttm(income, SHARES, PRICE)
    assert ttm.market_cap == round(PRICE * SHARES, 0)
    assert ttm.market_cap_source == "derived"
    assert ttm.market_cap_check_pct is None


def test_small_cap_uses_reported_cap_despite_garbage_shares(income):
    """The production bug: stale/misparsed share count understated the derived
    mcap and a >1 mld PLN company scored 'small'. The reported figure wins."""
    ttm = m.compute_ttm(
        income, shares_outstanding=852_912, price=330.80,  # 10× too few shares
        reported_market_cap=2_821_435_788.0,
    )
    assert ttm.market_cap == 2_821_435_788.0
    quarters = m.compute_quarter_metrics(income)
    prescore = m.compute_prescore(
        quarters, ttm, m.compute_pe_history(CZ_HISTORY, ttm.pe),
        22000.0, "x", [2025],
    )
    small_cap = next(c for c in prescore.checks if c.id == "small_cap")
    assert small_cap.verdict == "fail"
    assert "wg BiznesRadar" in small_cap.evidence
    assert "Średnia spółka" in small_cap.evidence


def test_reverse_gross_derivation():
    """Layouts that report profit-on-sales + both cost lines but no gross row:
    gross = pos + selling + admin, so the key margin exists for them too."""
    series = {
        "2025Q1": {
            "profit_on_sales": 10_000.0,
            "selling_costs": 8_000.0,
            "admin_costs": 6_000.0,
        }
    }
    assert m.derive_income_fields(series)["2025Q1"]["gross_profit"] == 24_000.0
