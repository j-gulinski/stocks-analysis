"""Dynamic per-company analysis (services/insights.py) — pure unit tests.

Three archetypes prove the layer adapts to the company instead of forcing one
checklist on everything: a small industrial with full data, a bank with no
classic income statement, and a cash-burning biotech. The honesty rules are
asserted explicitly: missing numbers land in `missing` with a why, never as
fabricated verdicts, and stale/derived inputs produce data_notes.
"""
import pytest

from app.services import insights


# ------------------------------------------------------------- sector groups

@pytest.mark.parametrize(
    ("sector", "group"),
    [
        ("Banki", "finance"),
        ("Ubezpieczenia", "finance"),
        ("Biotechnologia", "biotech_med"),
        ("Gry komputerowe", "tech"),
        ("Informatyka", "tech"),
        ("Przemysł elektromaszynowy", "industrial"),
        ("Materiały budowlane", "industrial"),
        ("Deweloperzy", "realestate"),
        ("Energetyka", "energy"),
        ("Handel detaliczny", "consumer"),
        ("Coś egzotycznego", "other"),
        (None, "other"),
    ],
)
def test_classify_sector(sector, group):
    assert insights.classify_sector(sector) == group


# ------------------------------------------------------------------ fixtures

def _industrial_quarters():
    periods = [f"{y}Q{q}" for y in (2024, 2025, 2026) for q in (1, 2, 3, 4)]
    return [
        {
            "period": period,
            "revenue": 10_000 + 500 * i,
            "revenue_yoy_pct": 12.0,
            "gross_margin_pct": 30.0 + 0.5 * i,
            "sales_margin_pct": 15.0,
            "net_margin_pct": 10.0,
            "profit_on_sales": 1_500.0 + 30 * i,
            "operating_profit": 1_600.0,
            "net_profit": 1_200.0,
            "one_off_share_pct": 8.0,
        }
        for i, period in enumerate(periods)
    ]


# ----------------------------------------------------- industrial, full data

def test_industrial_full_data():
    result = insights.build_insights(
        sector="Przemysł elektromaszynowy",
        quarters=_industrial_quarters(),
        ttm={"net_profit": 4_800.0, "eps": 0.56, "pe": 9.5, "market_cap": 450e6,
             "price": 5.4, "market_cap_source": "reported",
             "market_cap_check_pct": 2.0},
        pe_history={"median": 14.0, "q1": 10.0, "q3": 18.0, "current": 9.5,
                    "percentile": 20.0},
        net_cash_value=12_000.0,
        balance_latest={"equity": 80_000.0, "current_assets": 50_000.0,
                        "current_liabilities": 25_000.0},
        indicators_latest={"roe": ("2026Q1", 15.2), "cwk": ("2026Q1", 1.4),
                           "ev_ebitda": ("2026Q1", 5.5)},
        dividend_years=[2023, 2024, 2025],
        dividend_yield_latest=3.2,
        price_age_days=1,
    ).to_dict()

    assert result["size_code"] == "small"
    assert result["sector_group"] == "industrial"
    ids = [i["id"] for i in result["key_indicators"]]
    # the industrial playbook leads with the gross-sales margin (Malik's key)
    assert ids[0] == "gross_margin"
    assert "operating_leverage" in ids
    pe = next(i for i in result["key_indicators"] if i["id"] == "pe_vs_history")
    assert pe["verdict"] == "good"  # 9.5 well under own median 14
    assert len(result["strengths"]) >= 2
    assert result["missing"] == []  # full data → nothing to apologize for
    assert result["coverage"]["available"] == result["coverage"]["selected"]
    assert "plus" in result["summary"].lower()


def test_gross_margin_trend_uses_pl_decimal_comma():
    """Regression: the margin-trend p.p. in the comment must use the decimal
    comma and match the summary brief (comment '+1.5' vs brief '+1,5' was the
    bug). Rising 30.0→35.5% margin over 12 quarters → trend +1,5 p.p."""
    result = insights.build_insights(
        sector="Przemysł elektromaszynowy",
        quarters=_industrial_quarters(),
        ttm={"net_profit": 4_800.0, "eps": 0.56, "pe": 9.5, "market_cap": 450e6,
             "price": 5.4, "market_cap_source": "reported",
             "market_cap_check_pct": 2.0},
        pe_history={"median": 14.0, "q1": 10.0, "q3": 18.0, "current": 9.5,
                    "percentile": 20.0},
        net_cash_value=12_000.0,
        balance_latest={"equity": 80_000.0, "current_assets": 50_000.0,
                        "current_liabilities": 25_000.0},
        indicators_latest={},
        dividend_years=[],
        dividend_yield_latest=None,
        price_age_days=1,
    ).to_dict()
    gm = next(i for i in result["key_indicators"] if i["id"] == "gross_margin")
    assert "+1,5 p.p." in gm["comment"]
    assert "+1.5" not in gm["comment"]
    # the composed summary reuses the same comma form — no dot/comma drift
    assert "+1.5" not in result["summary"]


def test_discontinued_result_is_a_bad_one_off_signal():
    quarters = _industrial_quarters()
    quarters[-1] = {
        **quarters[-1],
        "one_off_share_pct": 477.7,
        "discontinued_profit": 256_562.0,
    }
    result = insights.build_insights(
        sector="Przemysł elektromaszynowy",
        quarters=quarters,
        ttm={"net_profit": 300_000.0, "eps": 30.0, "pe": 8.0,
             "market_cap": 450e6, "price": 240.0,
             "market_cap_source": "reported", "market_cap_check_pct": 2.0},
        pe_history={"median": 14.0, "q1": 10.0, "q3": 18.0, "current": 8.0,
                    "percentile": 10.0},
        net_cash_value=12_000.0,
        balance_latest={"equity": 80_000.0},
        indicators_latest={},
        dividend_years=[],
        dividend_yield_latest=None,
        price_age_days=1,
    ).to_dict()

    one_off = next(i for i in result["key_indicators"] if i["id"] == "one_offs")
    assert one_off["verdict"] == "bad"
    assert "działalność zaniechana 256 562 tys. zł" in one_off["comment"]
    assert "wynik netto i C/Z mogą być zniekształcone" in one_off["comment"]


# ------------------------------------------------ bank, no income statement

def test_bank_without_income_data_stays_honest():
    result = insights.build_insights(
        sector="Banki",
        quarters=[],  # classic revenue/margin rows don't exist for banks
        ttm={"net_profit": None, "eps": None, "pe": None, "market_cap": 8e9,
             "price": 120.0, "market_cap_source": "reported",
             "market_cap_check_pct": None},
        pe_history={"median": None, "q1": None, "q3": None, "current": None,
                    "percentile": None},
        net_cash_value=None,
        balance_latest={},
        indicators_latest={"roe": ("2026Q1", 13.0), "cwk": ("2026Q1", 1.1)},
        dividend_years=[2024, 2025],
        dividend_yield_latest=5.5,
        price_age_days=2,
    ).to_dict()

    assert result["sector_group"] == "finance"
    assert result["size_code"] == "large"
    ids = [i["id"] for i in result["key_indicators"]]
    # the finance playbook judges by ROE / C/WK / dividend, not margins
    assert {"roe", "cwk", "dividend"} <= set(ids)
    assert "revenue_growth" not in ids  # absent data is NOT fabricated
    missing_ids = [miss["id"] for miss in result["missing"]]
    assert "pe_vs_history" in missing_ids
    assert all(miss["why"] for miss in result["missing"])
    assert any("finansowa" in note for note in result["data_notes"])
    # honest, partial-coverage summary + out-of-sweet-spot warning
    assert result["coverage"]["available"] < result["coverage"]["selected"]
    assert "sweet spot" in result["summary"]


# ------------------------------------------------- biotech burning cash

def test_biotech_cash_burn_runway():
    result = insights.build_insights(
        sector="Biotechnologia",
        quarters=[{
            "period": "2025Q4", "revenue": 500.0, "revenue_yoy_pct": 40.0,
            "gross_margin_pct": None, "sales_margin_pct": None,
            "net_margin_pct": None, "profit_on_sales": None,
            "operating_profit": None, "net_profit": -3_000.0,
            "one_off_share_pct": None,
        }],
        ttm={"net_profit": -12_000.0, "eps": None, "pe": None,
             "market_cap": 300e6, "price": 12.0,
             "market_cap_source": "derived", "market_cap_check_pct": None},
        pe_history={"median": 20.0, "q1": None, "q3": None, "current": None,
                    "percentile": None},
        net_cash_value=30_000.0,  # tys. PLN vs 12 000 tys. burn → ~2.5 roku
        balance_latest={},
        indicators_latest={},
        dividend_years=[],
        dividend_yield_latest=None,
        price_age_days=30,
    ).to_dict()

    assert result["sector_group"] == "biotech_med"
    runway = next(i for i in result["key_indicators"] if i["id"] == "cash_runway")
    assert runway["verdict"] == "good"  # 30 000 / 12 000 = 2.5 years
    assert "2.5" in runway["value"] or "2,5" in runway["value"]
    # stale price and derived mcap must both be flagged
    assert any("Kurs sprzed" in note for note in result["data_notes"])
    assert any("przybliżenie" in note for note in result["data_notes"])
    assert result["coverage"]["available"] < result["coverage"]["selected"]
