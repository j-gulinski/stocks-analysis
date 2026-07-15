"""Economic contracts for the canonical valuation-engine-v4 potential bridge."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.api.schemas import (
    ValuationMethodology,
    ValuationProbabilityModel,
    ValuationRequestIn,
    ValuationScenarioAssumptions,
)
from app.services.valuation_engine import (
    ValuationInputError,
    calculate_valuation,
    derive_scenario_probabilities,
    probability_weighted,
    validate_assumption_bindings,
)


def _value(value: float, *, basis: str = "codex_judgment", fact_ids=()) -> dict:
    return {
        "value": value,
        "basis": basis,
        "rationale": "Company-specific explicit test assumption with no hidden default.",
        "source_fact_ids": list(fact_ids),
        "research_claim_paths": [],
    }


def _scenario(
    kind: str,
    *,
    revenue_scale: float = 1.0,
    capex_pct: float = 4.0,
    event_pnl: float | None = None,
    event_cash: float = 0.0,
    event_period: str = "2028",
) -> ValuationScenarioAssumptions:
    years = []
    for offset, period in enumerate(range(2026, 2031)):
        years.append(
            {
                "period": str(period),
                "revenue_pln_thousands": _value(
                    (100_000 + offset * 10_000) * revenue_scale
                ),
                "ebitda_margin_pct": _value(20.0),
                "depreciation_pct_revenue": _value(3.0),
                "capex_pct_revenue": _value(capex_pct),
                "delta_nwc_pct_revenue": _value(1.0),
                "cash_tax_rate_pct": _value(19.0),
                "net_financial_result_pct_revenue": _value(-1.0),
                "fcff_period_fraction": _value(0.5 if offset == 0 else 1.0),
                "fcff_discount_years": _value(0.5 + offset),
            }
        )
    cumulative_cash_after_financing_to_valuation = 0.0
    for year in years[:3]:
        revenue = year["revenue_pln_thousands"]["value"]
        ebit = revenue * (
            year["ebitda_margin_pct"]["value"]
            - year["depreciation_pct_revenue"]["value"]
        ) / 100.0
        financial_result = (
            revenue
            * year["net_financial_result_pct_revenue"]["value"]
            / 100.0
        )
        pretax = ebit + financial_result
        cash_tax = max(pretax, 0.0) * year["cash_tax_rate_pct"]["value"] / 100.0
        recurring_net_result = pretax - cash_tax
        cash_after_financing = (
            recurring_net_result
            + revenue * year["depreciation_pct_revenue"]["value"] / 100.0
            - revenue * year["capex_pct_revenue"]["value"] / 100.0
            - revenue * year["delta_nwc_pct_revenue"]["value"] / 100.0
        )
        cumulative_cash_after_financing_to_valuation += (
            cash_after_financing * year["fcff_period_fraction"]["value"]
        )
    event_cash_to_valuation = (
        event_cash
        if event_pnl is not None and event_period <= "2028"
        else 0.0
    )
    return ValuationScenarioAssumptions.model_validate(
        {
            "kind": kind,
            "label": kind,
            "forecast_years": years,
            "potential_drivers": [
                {
                    "driver_id": "organic-growth",
                    "research_driver_key": "organic-growth",
                    "label": "Organic growth",
                    "mechanism": (
                        "Company-specific volume and pricing evidence changes the explicit revenue path."
                    ),
                    "runway_evidence": (
                        "The test bridge carries a distinct annual contribution through the full horizon."
                    ),
                    "capital_requirements": (
                        "Capex and working-capital ratios stay explicit and are not inferred from growth."
                    ),
                    "impacts": [
                        {
                            "period": str(period),
                            "revenue_delta_pln_thousands": _value(
                                100_000 * (revenue_scale - 1.0)
                                if period == 2026
                                else 10_000 * revenue_scale
                            ),
                            "ebitda_margin_delta_pp": None,
                            "depreciation_pct_revenue_delta_pp": None,
                            "capex_pct_revenue_delta_pp": (
                                _value(capex_pct - 4.0) if period == 2026 else None
                            ),
                            "delta_nwc_pct_revenue_delta_pp": None,
                            "cash_tax_rate_delta_pp": None,
                            "net_financial_result_pct_revenue_delta_pp": None,
                        }
                        for period in range(2026, 2031)
                    ],
                }
            ],
            "target_pe": _value(12.0),
            "target_ev_ebitda": _value(8.0),
            "target_ev_ebit": _value(10.0),
            "target_net_debt_pln_thousands": _value(
                20_000.0 - event_cash_to_valuation
            ),
            "cumulative_capital_allocation_pln_thousands": _value(
                cumulative_cash_after_financing_to_valuation
            ),
            "wacc_pct": _value(10.0),
            "terminal_growth_pct": _value(2.0),
            "terminal_reinvestment_rate_pct": _value(20.0),
            "terminal_incremental_roic_pct": _value(10.0),
            "event_impact": (
                {
                    "period": event_period,
                    "recurring": False,
                    "pnl_net_pln_thousands": _value(event_pnl),
                    "cash_pln_thousands": _value(event_cash),
                }
                if event_pnl is not None
                else None
            ),
        }
    )


def test_valuation_driver_accepts_every_valid_research_driver_key_shape():
    scenario = _scenario("base").model_dump(mode="json")
    scenario["potential_drivers"][0]["research_driver_key"] = "Operating Volume"

    validated = ValuationScenarioAssumptions.model_validate(scenario)

    assert validated.potential_drivers[0].research_driver_key == "Operating Volume"


def _methodology(primary: str = "fcff_dcf") -> ValuationMethodology:
    cross_checks = {
        "pe": ["fcff_dcf", "ev_ebitda"],
        "ev_ebitda": ["fcff_dcf", "pe"],
        "ev_ebit": ["fcff_dcf", "pe"],
        "fcff_dcf": ["pe", "ev_ebitda"],
    }[primary]
    return ValuationMethodology.model_validate(
        {
            "primary_method": primary,
            "cross_checks": cross_checks,
            "valuation_period": "2028",
            "rationale": (
                "FCFF is primary because operating cash reinvestment matters; recurring "
                "earnings and enterprise multiples are independent cross-checks."
            ),
        }
    )


def _base(*, net_debt_pln: float | None = 20_000_000) -> dict:
    return {
        "company": {
            "shares_outstanding": 1_000_000,
            "market_cap_pln": 120_000_000,
            "enterprise_value_pln": 140_000_000,
            "net_debt_pln": net_debt_pln,
        },
        "price": {"close_pln": 120.0},
        "street_expectations": {
            "provider": "biznesradar",
            "periods": {
                "2026": {
                    "revenue_pln_thousands": 95_000.0,
                    "net_income_pln_thousands": 12_000.0,
                },
                "2027": {"revenue_pln_thousands": 108_000.0},
                "2028": {
                    "revenue_pln_thousands": 118_000.0,
                    "revenue_pln_thousands_range": {
                        "low": 110_000.0,
                        "high": 125_000.0,
                        "forecast_count": 6,
                    },
                },
            },
        },
    }


def test_five_year_engine_compares_street_and_calculates_independent_methods():
    result = calculate_valuation(_base(), [_scenario("base")], _methodology())
    row = result["scenarios"][0]

    assert len(row["forecast_path"]) == 5
    assert all(item["status"] == "calculated" for item in row["methods"].values())
    bridge = next(item for item in row["expectation_bridge"] if item["period"] == "2028")
    revenue = next(item for item in bridge["metrics"] if item["metric"] == "revenue")
    assert revenue["street_pln_thousands"] == 118_000.0
    assert revenue["variance_pct"] == pytest.approx(1.69)
    assert row["target_price_pln"] == row["methods"]["fcff_dcf"]["price_pln"]
    assert row["target_price_basis"] == "present"
    assert row["cross_check_range_pln"] is None


def test_driver_to_value_bridge_exposes_runway_reinvestment_and_market_hurdles():
    result = calculate_valuation(_base(), [_scenario("base")], _methodology())
    bridge = result["scenarios"][0]["driver_to_value_bridge"]

    assert bridge["drivers"] == [
        {
            "driver_id": "organic-growth",
            "research_driver_key": "organic-growth",
                "impacts": [
                    {
                        "period": str(period),
                        "revenue_delta_pln_thousands": (
                            0.0 if period == 2026 else 10_000.0
                        ),
                        "ebitda_margin_delta_pp": None,
                        "depreciation_pct_revenue_delta_pp": None,
                        "capex_pct_revenue_delta_pp": (
                            0.0 if period == 2026 else None
                        ),
                        "delta_nwc_pct_revenue_delta_pp": None,
                        "cash_tax_rate_delta_pp": None,
                        "net_financial_result_pct_revenue_delta_pp": None,
                    }
                    for period in range(2026, 2031)
            ],
            "cumulative_revenue_delta_pln_thousands": 40_000.0,
            "cumulative_ebitda_margin_delta_pp": 0.0,
            "cumulative_depreciation_ratio_delta_pp": 0.0,
            "cumulative_capex_ratio_delta_pp": 0.0,
            "cumulative_nwc_ratio_delta_pp": 0.0,
            "cumulative_cash_tax_rate_delta_pp": 0.0,
            "cumulative_net_financial_result_ratio_delta_pp": 0.0,
            "runway_end_period": "2030",
        }
    ]
    assert bridge["trajectory"]["revenue"]["cagr_pct"] == pytest.approx(8.78)
    assert bridge["reinvestment"]["cumulative_capex_pln_thousands"] > 0
    assert bridge["reinvestment"]["capex_to_depreciation_pct"] > 100
    assert bridge["terminal_economics"] == {
        "growth_pct": 2.0,
        "reinvestment_rate_pct": 20.0,
        "incremental_roic_pct": 10.0,
        "terminal_value_share_pct": bridge["terminal_economics"]["terminal_value_share_pct"],
    }
    assert bridge["market_hurdles"]["pe"]["status"] == "calculated"
    assert bridge["market_hurdles"]["fcff_dcf"]["held_constant"] == (
        "margin, reinvestment ratios, WACC, terminal economics and timed event cash"
    )
    assert bridge["net_debt_bridge"]["reconciliation_residual_pln_thousands"] == 0
    assert bridge["net_debt_bridge"][
        "cumulative_cash_after_financing_to_valuation_pln_thousands"
    ] == pytest.approx(30_688.0)
    assert bridge["price_change_basis"] == "present_value_gap"
    assert bridge["current_value_gap_pct"] is not None
    assert bridge["annualized_price_repricing_pct"] is None


def test_future_multiple_prices_annualize_and_compare_only_on_the_same_value_date():
    row = calculate_valuation(
        _base(), [_scenario("base")], _methodology("pe")
    )["scenarios"][0]

    assert row["target_price_basis"] == "future_fiscal_period"
    assert row["target_price_period"] == "2028"
    assert row["cross_check_range_pln"]["low"] < row["cross_check_range_pln"]["high"]
    assert row["driver_to_value_bridge"]["annualized_price_repricing_pct"] is not None


def test_request_requires_one_shared_nonpast_scenario_clock():
    scenarios = [_scenario("negative"), _scenario("base"), _scenario("positive")]
    scenarios[0].forecast_years[0].fcff_discount_years.value = 0.75

    with pytest.raises(ValueError, match="all scenarios must share"):
        ValuationRequestIn.model_validate(
            {
                "research_snapshot_id": 1,
                "assumptions": scenarios,
                "methodology": _methodology(),
                "as_of": datetime(2026, 7, 15, tzinfo=timezone.utc),
            }
        )

    with pytest.raises(ValueError, match="forecast anchor must be"):
        ValuationRequestIn.model_validate(
            {
                "research_snapshot_id": 1,
                "assumptions": [
                    _scenario("negative"),
                    _scenario("base"),
                    _scenario("positive"),
                ],
                "methodology": _methodology(),
                "as_of": datetime(2028, 1, 1, tzinfo=timezone.utc),
            }
        )

    with pytest.raises(ValueError, match="event scenario requires FCFF DCF"):
        ValuationRequestIn.model_validate(
            {
                "research_snapshot_id": 1,
                "assumptions": [
                    _scenario("negative"),
                    _scenario("base"),
                    _scenario("positive"),
                    _scenario("event", event_pnl=0),
                ],
                "methodology": _methodology("pe"),
                "as_of": datetime(2026, 7, 15, tzinfo=timezone.utc),
            }
        )

    mismatched = [
        _scenario("negative"),
        _scenario("base"),
        _scenario("positive"),
    ]
    mismatched[0].potential_drivers[0].research_driver_key = "other-driver"
    with pytest.raises(ValueError, match="one label and Research key"):
        ValuationRequestIn.model_validate(
            {
                "research_snapshot_id": 1,
                "assumptions": mismatched,
                "methodology": _methodology(),
                "as_of": datetime(2026, 7, 15, tzinfo=timezone.utc),
            }
        )

    unbridged_anchor = [
        _scenario("negative"),
        _scenario("base"),
        _scenario("positive"),
    ]
    for year in unbridged_anchor[0].forecast_years:
        year.revenue_pln_thousands.value += 1_000
    with pytest.raises(ValueError, match="anchor revenue_pln_thousands"):
        ValuationRequestIn.model_validate(
            {
                "research_snapshot_id": 1,
                "assumptions": unbridged_anchor,
                "methodology": _methodology(),
                "as_of": datetime(2026, 7, 15, tzinfo=timezone.utc),
            }
        )


def test_potential_driver_deltas_must_reconcile_to_the_forecast_path():
    raw = _scenario("base").model_dump(mode="json")
    raw["potential_drivers"][0]["impacts"][1][
        "revenue_delta_pln_thousands"
    ]["value"] = 9_000

    with pytest.raises(ValueError, match="do not reconcile revenue_pln_thousands for 2027"):
        ValuationScenarioAssumptions.model_validate(raw)


def test_shared_driver_may_be_explicitly_dormant_in_one_scenario():
    raw = _scenario("base").model_dump(mode="json")
    for year in raw["forecast_years"]:
        year["revenue_pln_thousands"]["value"] = 100_000
    for impact in raw["potential_drivers"][0]["impacts"]:
        impact["revenue_delta_pln_thousands"]["value"] = 0
        impact["revenue_delta_pln_thousands"]["research_claim_paths"] = [
            "outlook.drivers[0]"
        ]

    scenario = ValuationScenarioAssumptions.model_validate(raw)
    assert all(
        impact.revenue_delta_pln_thousands.value == 0
        for impact in scenario.potential_drivers[0].impacts
    )


def test_terminal_growth_requires_reinvestment_times_incremental_roic():
    raw = _scenario("base").model_dump(mode="json")
    raw["terminal_incremental_roic_pct"]["value"] = 8.0

    with pytest.raises(ValueError, match="terminal growth must reconcile"):
        ValuationScenarioAssumptions.model_validate(raw)


def test_capex_changes_intrinsic_value_but_not_earnings_multiple_methods():
    low = calculate_valuation(
        _base(), [_scenario("base", capex_pct=2.0)], _methodology()
    )["scenarios"][0]["methods"]
    high = calculate_valuation(
        _base(), [_scenario("base", capex_pct=9.0)], _methodology()
    )["scenarios"][0]["methods"]

    assert high["fcff_dcf"]["price_pln"] < low["fcff_dcf"]["price_pln"]
    assert high["pe"]["price_pln"] == low["pe"]["price_pln"]
    assert high["ev_ebitda"]["price_pln"] == low["ev_ebitda"]["price_pln"]


def test_future_ev_methods_use_an_explicit_reconciled_target_net_debt():
    original = calculate_valuation(
        _base(), [_scenario("base")], _methodology("pe")
    )["scenarios"][0]
    raw = _scenario("base").model_dump(mode="json")
    raw["target_net_debt_pln_thousands"]["value"] -= 5_000
    raw["cumulative_capital_allocation_pln_thousands"]["value"] -= 5_000
    lower_debt = calculate_valuation(
        _base(),
        [ValuationScenarioAssumptions.model_validate(raw)],
        _methodology("pe"),
    )["scenarios"][0]

    assert lower_debt["methods"]["ev_ebitda"]["price_pln"] == pytest.approx(
        original["methods"]["ev_ebitda"]["price_pln"] + 5.0
    )

    raw["target_net_debt_pln_thousands"]["value"] += 1
    with pytest.raises(ValuationInputError, match="Target net debt does not reconcile"):
        calculate_valuation(
            _base(),
            [ValuationScenarioAssumptions.model_validate(raw)],
            _methodology("pe"),
        )


def test_enterprise_multiple_is_unavailable_for_nonpositive_metric():
    raw = _scenario("negative").model_dump(mode="json")
    for year in raw["forecast_years"]:
        year["ebitda_margin_pct"]["value"] = -10.0
    raw["potential_drivers"][0]["impacts"][0][
        "ebitda_margin_delta_pp"
    ] = _value(-30.0)
    raw["cumulative_capital_allocation_pln_thousands"]["value"] = -44_800.0
    scenario = ValuationScenarioAssumptions.model_validate(raw)

    row = calculate_valuation(
        _base(), [scenario], _methodology("ev_ebitda")
    )["scenarios"][0]

    assert row["methods"]["ev_ebitda"]["status"] == "unavailable"
    assert "positive operating denominator" in row["methods"]["ev_ebitda"]["gap"]
    assert row["target_price_pln"] is None


def test_nonrecurring_event_is_not_capitalized_as_recurring_earnings():
    no_event = calculate_valuation(
        _base(), [_scenario("event", event_pnl=0, event_cash=0)], _methodology()
    )["scenarios"][0]
    event = calculate_valuation(
        _base(), [_scenario("event", event_pnl=50_000, event_cash=10_000)], _methodology()
    )["scenarios"][0]

    no_event_2028 = no_event["forecast_path"][2]
    event_2028 = event["forecast_path"][2]
    assert event_2028["reported_net_result_pln_thousands"] == (
        no_event_2028["reported_net_result_pln_thousands"] + 50_000
    )
    assert event_2028["recurring_net_result_pln_thousands"] == no_event_2028[
        "recurring_net_result_pln_thousands"
    ]
    assert event["methods"]["pe"]["status"] == "unavailable"
    assert event["methods"]["ev_ebitda"]["status"] == "unavailable"
    assert event["methods"]["fcff_dcf"]["price_pln"] > no_event["methods"]["fcff_dcf"]["price_pln"]


def test_event_cash_is_discounted_at_its_own_period():
    early = calculate_valuation(
        _base(),
        [_scenario("event", event_pnl=0, event_cash=10_000, event_period="2028")],
        _methodology(),
    )["scenarios"][0]["methods"]["fcff_dcf"]
    late = calculate_valuation(
        _base(),
        [_scenario("event", event_pnl=0, event_cash=10_000, event_period="2030")],
        _methodology(),
    )["scenarios"][0]["methods"]["fcff_dcf"]

    assert early["event_cash_present_value_pln_thousands"] > late[
        "event_cash_present_value_pln_thousands"
    ]
    assert early["price_pln"] > late["price_pln"]


def test_unknown_net_debt_disables_ev_and_dcf_without_assuming_zero():
    row = calculate_valuation(
        _base(net_debt_pln=None), [_scenario("base")], _methodology("pe")
    )["scenarios"][0]
    assert row["methods"]["pe"]["status"] == "calculated"
    assert row["methods"]["ev_ebitda"] == {"status": "unavailable", "price_pln": None}
    assert row["methods"]["fcff_dcf"] == {"status": "unavailable", "price_pln": None}


def test_optional_method_inputs_are_explicit_not_hidden_defaults():
    raw = _scenario("base").model_dump(mode="json")
    del raw["wacc_pct"]
    with pytest.raises(ValueError, match="wacc_pct"):
        ValuationScenarioAssumptions.model_validate(raw)


def test_market_implied_forward_pe_cannot_anchor_target_multiple():
    scenario = _scenario("base")
    raw = scenario.model_dump(mode="json")
    raw["target_pe"] = _value(16.87, basis="reported_fact", fact_ids=(99,))
    scenario = ValuationScenarioAssumptions.model_validate(raw)
    manifest = {
        "bindable_fact_ids": [99],
        "fact_catalog": {"99": {"fact_key": "market_implied.forward_pe"}},
        "research_claim_catalog": {},
    }
    with pytest.raises(ValuationInputError, match="cannot anchor target P/E"):
        validate_assumption_bindings([scenario], manifest)


def test_street_assumption_requires_a_consensus_fact_key():
    raw = _scenario("base").model_dump(mode="json")
    raw["forecast_years"][0]["revenue_pln_thousands"] = _value(
        100_000, basis="street_estimate", fact_ids=(7,)
    )
    scenario = ValuationScenarioAssumptions.model_validate(raw)
    with pytest.raises(ValuationInputError, match="semantically matching consensus fact"):
        validate_assumption_bindings(
            [scenario],
            {
                "bindable_fact_ids": [7],
                "fact_catalog": {"7": {"fact_key": "income.IncomeRevenues"}},
                "research_claim_catalog": {},
            },
        )


def test_research_claim_binding_requires_frozen_text_and_source_lineage():
    raw = _scenario("base").model_dump(mode="json")
    raw["target_pe"]["research_claim_paths"] = ["/sections/thesis/why_now"]
    scenario = ValuationScenarioAssumptions.model_validate(raw)

    with pytest.raises(ValuationInputError, match="lost their frozen text/source lineage"):
        validate_assumption_bindings(
            [scenario],
            {
                "bindable_fact_ids": [],
                "fact_catalog": {},
                "research_claim_catalog": {
                    "/sections/thesis/why_now": {
                        "kind": "fact",
                        "text": None,
                        "source_version_ids": [],
                    }
                },
            },
        )


def test_conditional_probability_tree_is_recomputed_and_weighted():
    model = ValuationProbabilityModel.model_validate(
        {
            "posture": "judgmental_unvalidated",
            "nodes": [
                {
                    "node_id": "down",
                    "parent_id": None,
                    "condition": "Demand and backlog conversion weaken materially.",
                    "conditional_probability_pct": 25,
                    "basis": "judgment",
                    "rationale": "Company-specific counter-thesis judgment with evidence still requiring calibration.",
                    "scenario_kind": "negative",
                },
                {
                    "node_id": "base",
                    "parent_id": None,
                    "condition": "Current order conversion remains near the retained expectation curve.",
                    "conditional_probability_pct": 50,
                    "basis": "judgment",
                    "rationale": "Company-specific central path judgment with no empirical calibration claim.",
                    "scenario_kind": "base",
                },
                {
                    "node_id": "up",
                    "parent_id": None,
                    "condition": "Evidence confirms faster conversion and durable margins.",
                    "conditional_probability_pct": 25,
                    "basis": "judgment",
                    "rationale": "Company-specific upside path judgment with no empirical calibration claim.",
                    "scenario_kind": "positive",
                },
            ],
            "dataset_fingerprint": None,
            "brier_score": None,
        }
    )
    probabilities = derive_scenario_probabilities(
        model, {"negative", "base", "positive"}
    )
    outputs = calculate_valuation(
        _base(),
        [
            _scenario("negative", revenue_scale=0.8),
            _scenario("base"),
            _scenario("positive", revenue_scale=1.2),
        ],
        _methodology(),
    )
    weighted = probability_weighted(outputs, probabilities)

    assert [row["probability_pct"] for row in probabilities] == [50.0, 25.0, 25.0]
    assert weighted["status"] == "calculated"
    assert weighted["price_pln"] is not None


def test_probability_tree_rejects_non_exhaustive_root():
    model = ValuationProbabilityModel.model_validate(
        {
            "posture": "judgmental_unvalidated",
            "nodes": [
                {
                    "node_id": "only",
                    "condition": "Only one partial branch was supplied here.",
                    "conditional_probability_pct": 60,
                    "basis": "judgment",
                    "rationale": "This deliberately incomplete probability tree must fail deterministic validation.",
                    "scenario_kind": "base",
                }
            ],
            "dataset_fingerprint": None,
            "brier_score": None,
        }
    )
    with pytest.raises(ValuationInputError, match="sum to 60"):
        derive_scenario_probabilities(model, {"base"})


def test_calibrated_probability_claim_requires_auditable_dataset_evidence():
    with pytest.raises(ValueError, match="reliability bins"):
        ValuationProbabilityModel.model_validate(
            {
                "posture": "empirical_calibrated",
                "nodes": [
                    {
                        "node_id": "base",
                        "condition": "Point-in-time dataset assigns this terminal state.",
                        "conditional_probability_pct": 99,
                        "basis": "empirical_frequency",
                        "numerator": 99,
                        "denominator": 100,
                        "rationale": "A calibration claim without complete validation artifacts must be rejected.",
                        "scenario_kind": "base",
                    }
                ],
                "dataset_fingerprint": "a" * 64,
                "brier_score": 0.2,
            }
        )
