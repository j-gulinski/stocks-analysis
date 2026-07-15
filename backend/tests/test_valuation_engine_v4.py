"""Economic validity tests for the canonical valuation-engine-v4 work."""

import pytest

from app.services.valuation_engine import (
    calculate_dcf_sensitivity,
    ValuationInputError,
    calculate_fcff_dcf,
    classify_forward_pe_identity,
    ev_to_equity_price,
    solve_reverse_dcf_revenue_scale,
)


def test_dcf_sensitivity_skips_infeasible_terminal_reinvestment_cells():
    forecast = [{
        "period": "2027",
        "ebit_pln_thousands": 100,
        "tax_rate_pct": 20,
        "depreciation_pln_thousands": 10,
        "capex_pln_thousands": 20,
        "delta_nwc_pln_thousands": 5,
        "fcff_period_fraction": 1.0,
        "fcff_discount_years": 1.0,
    }]

    grid = calculate_dcf_sensitivity(
        forecast,
        wacc_pct=10,
        terminal_growth_pct=2,
        terminal_reinvestment_rate_pct=100,
        terminal_incremental_roic_pct=2,
        net_debt_pln_thousands=0,
        shares_outstanding=1_000,
    )

    assert grid
    assert any(row["terminal_growth_pct"] == 2 for row in grid)
    assert all(
        -100 <= row["terminal_reinvestment_rate_pct"] <= 100 for row in grid
    )
    assert not any(row["terminal_growth_pct"] == 2.5 for row in grid)


def test_snt_consensus_pe_is_current_trading_identity_not_target_multiple():
    result = classify_forward_pe_identity(
        {
            "2026": {"net_income_pln_thousands": 158_300, "forward_pe": 21.14},
            "2027": {"net_income_pln_thousands": 176_000, "forward_pe": 19.02},
            "2028": {"net_income_pln_thousands": 198_400, "forward_pe": 16.87},
        },
        market_cap_pln=3_346_830_134,
        shares_outstanding=8_529_129,
    )

    assert result["classification"] == "current_trading_multiple_identity"
    assert result["not_a_target_multiple"] is True
    assert [row["implied_price_pln"] for row in result["rows"]] == [
        392.3568,
        392.4809,
        392.4208,
    ]


def test_fcff_dcf_hand_calculation_and_cash_dependencies():
    base = [
        {
            "period": "2027",
            "ebit_pln_thousands": 100,
            "tax_rate_pct": 20,
            "depreciation_pln_thousands": 10,
            "capex_pln_thousands": 20,
            "delta_nwc_pln_thousands": 5,
            "fcff_period_fraction": 1.0,
            "fcff_discount_years": 1.0,
        },
        {
            "period": "2028",
            "ebit_pln_thousands": 110,
            "tax_rate_pct": 20,
            "depreciation_pln_thousands": 11,
            "capex_pln_thousands": 22,
            "delta_nwc_pln_thousands": 5,
            "fcff_period_fraction": 1.0,
            "fcff_discount_years": 2.0,
        },
    ]
    result = calculate_fcff_dcf(
        base,
        wacc_pct=10,
        terminal_growth_pct=2,
        terminal_reinvestment_rate_pct=20,
        terminal_incremental_roic_pct=10,
        net_debt_pln_thousands=50,
        shares_outstanding=1_000,
    )

    assert [row["fcff_pln_thousands"] for row in result["forecast_years"]] == [65, 72]
    assert result["terminal_nopat_pln_thousands"] == 89.76
    assert result["terminal_fcff_pln_thousands"] == 71.81
    higher_capex = [dict(row) for row in base]
    higher_capex[1]["capex_pln_thousands"] = 40
    assert calculate_fcff_dcf(
        higher_capex,
        wacc_pct=10,
        terminal_growth_pct=2,
        terminal_reinvestment_rate_pct=20,
        terminal_incremental_roic_pct=10,
        net_debt_pln_thousands=50,
        shares_outstanding=1_000,
    )["price_pln"] < result["price_pln"]


def test_fcff_dcf_prorates_and_discounts_a_short_first_fiscal_period():
    full = [{
        "period": "2026",
        "ebit_pln_thousands": 100,
        "tax_rate_pct": 20,
        "depreciation_pln_thousands": 10,
        "capex_pln_thousands": 20,
        "delta_nwc_pln_thousands": 5,
        "fcff_period_fraction": 1.0,
        "fcff_discount_years": 1.0,
    }]
    stub = [{**full[0], "fcff_period_fraction": 0.25, "fcff_discount_years": 0.25}]

    full_result = calculate_fcff_dcf(
        full,
        wacc_pct=10,
        terminal_growth_pct=2,
        terminal_reinvestment_rate_pct=20,
        terminal_incremental_roic_pct=10,
        net_debt_pln_thousands=0,
        shares_outstanding=1_000,
    )
    stub_result = calculate_fcff_dcf(
        stub,
        wacc_pct=10,
        terminal_growth_pct=2,
        terminal_reinvestment_rate_pct=20,
        terminal_incremental_roic_pct=10,
        net_debt_pln_thousands=0,
        shares_outstanding=1_000,
    )

    first = stub_result["forecast_years"][0]
    assert first["annual_fcff_pln_thousands"] == 65
    assert first["fcff_pln_thousands"] == 16.25
    assert first["fcff_period_fraction"] == 0.25
    assert stub_result["enterprise_value_pln_thousands"] != full_result["enterprise_value_pln_thousands"]


def test_dcf_rejects_wacc_not_above_terminal_growth():
    with pytest.raises(ValuationInputError, match="WACC above terminal growth"):
        calculate_fcff_dcf(
            [{
                "ebit_pln_thousands": 100,
                "tax_rate_pct": 20,
                "depreciation_pln_thousands": 10,
                "capex_pln_thousands": 20,
                "delta_nwc_pln_thousands": 5,
                "fcff_period_fraction": 1.0,
                "fcff_discount_years": 1.0,
            }],
            wacc_pct=2,
            terminal_growth_pct=2,
            terminal_reinvestment_rate_pct=20,
            terminal_incremental_roic_pct=10,
            net_debt_pln_thousands=0,
            shares_outstanding=1_000,
        )


def test_ev_to_equity_bridge_reconciles():
    result = ev_to_equity_price(
        200_000,
        target_multiple=12,
        net_debt_pln_thousands=20_000,
        shares_outstanding=10_000_000,
    )

    assert result["enterprise_value_pln_thousands"] == 2_400_000
    assert result["equity_value_pln_thousands"] == 2_380_000
    assert result["price_pln"] == 238


def test_equity_values_are_floored_at_zero_in_distress():
    ev = ev_to_equity_price(
        100,
        target_multiple=2,
        net_debt_pln_thousands=500,
        shares_outstanding=1_000,
    )
    assert ev["raw_equity_value_pln_thousands"] == -300
    assert ev["distress_floor_applied"] is True
    assert ev["equity_value_pln_thousands"] == 0
    assert ev["price_pln"] == 0

    dcf = calculate_fcff_dcf(
        [{
            "period": "2027",
            "ebit_pln_thousands": 100,
            "tax_rate_pct": 20,
            "depreciation_pln_thousands": 10,
            "capex_pln_thousands": 20,
            "delta_nwc_pln_thousands": 5,
            "fcff_period_fraction": 1.0,
            "fcff_discount_years": 1.0,
        }],
        wacc_pct=10,
        terminal_growth_pct=2,
        terminal_reinvestment_rate_pct=20,
        terminal_incremental_roic_pct=10,
        net_debt_pln_thousands=10_000,
        shares_outstanding=1_000,
    )
    assert dcf["raw_equity_value_pln_thousands"] < 0
    assert dcf["distress_floor_applied"] is True
    assert dcf["price_pln"] == 0


def test_reverse_dcf_reprices_market_enterprise_value_with_negligible_residual():
    forecast = [
        {
            "period": str(period),
            "ebit_pln_thousands": 100 + offset * 10,
            "tax_rate_pct": 19,
            "depreciation_pln_thousands": 10,
            "capex_pln_thousands": 15,
            "delta_nwc_pln_thousands": 4,
            "fcff_period_fraction": 1.0,
            "fcff_discount_years": float(offset + 1),
        }
        for offset, period in enumerate(range(2026, 2031))
    ]
    market_ev = calculate_fcff_dcf(
        [{**row, **{
            key: row[key] * 1.4
            for key in (
                "ebit_pln_thousands",
                "depreciation_pln_thousands",
                "capex_pln_thousands",
                "delta_nwc_pln_thousands",
            )
        }} for row in forecast],
        wacc_pct=10,
        terminal_growth_pct=2,
        terminal_reinvestment_rate_pct=20,
        terminal_incremental_roic_pct=10,
        net_debt_pln_thousands=0,
        shares_outstanding=1,
    )["enterprise_value_pln_thousands"]

    solved = solve_reverse_dcf_revenue_scale(
        forecast,
        wacc_pct=10,
        terminal_growth_pct=2,
        terminal_reinvestment_rate_pct=20,
        terminal_incremental_roic_pct=10,
        market_enterprise_value_pln_thousands=market_ev,
    )

    assert solved["status"] == "calculated"
    assert solved["implied_revenue_path_scale_pct"] == pytest.approx(140.0, abs=0.001)
    assert solved["repricing_residual_bps"] <= 1.0
