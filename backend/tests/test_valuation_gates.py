"""Adversarial computed-evidence tests for VISION V4/V5 valuation gates."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.schemas import ValuationProbabilityModel, ValuationScenarioAssumptions
from app.services.valuation_gates import (
    _gate_evidence_binding,
    _gate_method_reconciliation,
    _gate_probability_structure,
    _gate_potential_driver_bridge,
    _gate_scenario_distinctness,
    _gate_unknown_neutrality,
    _scenario_vector,
    _vectors_near_duplicate,
)
from app.services.valuation_engine import calculate_valuation
from tests.test_valuation_v4 import _methodology, _scenario


def _probability_model(*, missingness: bool = False) -> ValuationProbabilityModel:
    rows = []
    for node_id, probability, kind in (
        ("down", 25, "negative"),
        ("central", 50, "base"),
        ("up", 25, "positive"),
    ):
        rows.append(
            {
                "node_id": node_id,
                "parent_id": None,
                "condition": (
                    "Missing source coverage pushes this outcome lower."
                    if missingness and kind == "negative"
                    else f"Company evidence supports the {kind} operating path."
                ),
                "conditional_probability_pct": probability,
                "basis": "judgment",
                "source_fact_ids": [],
                "research_claim_paths": [],
                "rationale": (
                    "Company-specific conditional judgment that remains explicitly uncalibrated by outcomes."
                ),
                "scenario_kind": kind,
            }
        )
    return ValuationProbabilityModel.model_validate(
        {
            "posture": "judgmental_unvalidated",
            "nodes": rows,
            "dataset_fingerprint": None,
            "brier_score": None,
        }
    )


def _draft(*, published=(25.0, 50.0, 25.0), missingness=False):
    assumptions = [_scenario("negative"), _scenario("base"), _scenario("positive")]
    judgment_rows = [
        SimpleNamespace(kind=kind, probability_pct=probability)
        for kind, probability in zip(
            ("negative", "base", "positive"), published, strict=True
        )
    ]
    return SimpleNamespace(
        assumptions=assumptions,
        methodology=_methodology(),
        codex_judgment=SimpleNamespace(
            probability_model=_probability_model(missingness=missingness),
            scenarios=judgment_rows,
        ),
        deterministic_outputs={"scenarios": []},
        gaps=[],
    )


def test_published_probabilities_must_reconcile_to_tree():
    result = _gate_probability_structure(_draft(published=(30.0, 45.0, 25.0)))
    assert result.passed is False
    assert "does not reconcile" in result.reason


def test_missingness_cannot_be_directional_probability_evidence():
    result = _gate_unknown_neutrality(_draft(missingness=True))
    assert result.passed is False
    assert "missingness" in result.reason


def test_all_codex_judgment_core_inputs_fail_evidence_anchor_gate():
    result = _gate_evidence_binding(_draft())
    assert result.passed is False
    assert "No core assumption" in result.reason


def test_potential_driver_gate_requires_evidence_and_computed_bridge_identity():
    draft = _draft()
    for scenario in draft.assumptions:
        scenario.potential_drivers[0].impacts[
            0
        ].revenue_delta_pln_thousands.source_fact_ids = [999]
    draft.input_manifest = {
        "research_claim_catalog": {
            "claims[0]": {
                "kind": "fact",
                "text": "Frozen company-specific operating evidence.",
                "source_version_ids": [1],
            }
        },
        "research_driver_catalog": {
            "organic-growth": {
                "label": "Organic growth",
                "claim_paths": ["claims[0]"],
            }
        },
    }
    missing = _gate_potential_driver_bridge(draft)
    assert missing.passed is False
    assert "no factual claim binding" in missing.reason

    for scenario in draft.assumptions:
        scenario.potential_drivers[0].impacts[0].revenue_delta_pln_thousands.research_claim_paths = [
            "claims[0]"
        ]
    draft.deterministic_outputs = calculate_valuation(
        {
            "company": {
                "shares_outstanding": 1_000_000,
                "market_cap_pln": 120_000_000,
                "enterprise_value_pln": 140_000_000,
                "net_debt_pln": 20_000_000,
            },
            "price": {"close_pln": 120.0},
            "street_expectations": {},
        },
        draft.assumptions,
        draft.methodology,
    )
    result = _gate_potential_driver_bridge(draft)
    assert result.passed is True
    assert "maximum reconciliation residual 0.000000" in result.reason


def test_event_potential_bridge_is_evidence_bound_and_preserved():
    draft = _draft()
    draft.assumptions.append(_scenario("event", event_pnl=0, event_cash=10_000))
    draft.input_manifest = {
        "research_claim_catalog": {
            "claims[0]": {
                "kind": "fact",
                "text": "Frozen company-specific operating evidence.",
                "source_version_ids": [1],
            }
        },
        "research_driver_catalog": {
            "organic-growth": {
                "label": "Organic growth",
                "claim_paths": ["claims[0]"],
            }
        },
    }
    for scenario in draft.assumptions[:-1]:
        scenario.potential_drivers[0].impacts[
            0
        ].revenue_delta_pln_thousands.research_claim_paths = ["claims[0]"]
    draft.assumptions[-1].potential_drivers[0].impacts[
        0
    ].revenue_delta_pln_thousands.source_fact_ids = [999]

    missing = _gate_potential_driver_bridge(draft)
    assert missing.passed is False
    assert "in event has no factual claim binding" in missing.reason

    draft.assumptions[-1].potential_drivers[0].impacts[
        0
    ].revenue_delta_pln_thousands.research_claim_paths = ["claims[0]"]
    draft.deterministic_outputs = calculate_valuation(
        {
            "company": {
                "shares_outstanding": 1_000_000,
                "market_cap_pln": 120_000_000,
                "enterprise_value_pln": 140_000_000,
                "net_debt_pln": 20_000_000,
            },
            "price": {"close_pln": 120.0},
            "street_expectations": {},
        },
        draft.assumptions,
        draft.methodology,
    )
    assert _gate_potential_driver_bridge(draft).passed is True


def test_potential_driver_cannot_relabel_its_frozen_research_driver():
    draft = _draft()
    for scenario in draft.assumptions:
        scenario.potential_drivers[0].label = "Debt refinancing"
    draft.input_manifest = {
        "research_claim_catalog": {
            "claims[0]": {
                "kind": "fact",
                "text": "Frozen company-specific operating evidence.",
                "source_version_ids": [1],
            }
        },
        "research_driver_catalog": {
            "organic-growth": {
                "label": "Organic growth",
                "claim_paths": ["claims[0]"],
            }
        },
    }

    result = _gate_potential_driver_bridge(draft)

    assert result.passed is False
    assert "changes the frozen Research-driver label" in result.reason


def test_event_cannot_reuse_a_driver_id_with_different_lineage():
    draft = _draft()
    event = _scenario("event", event_pnl=0)
    event.potential_drivers[0].research_driver_key = "different-driver"
    draft.assumptions.append(event)

    result = _gate_potential_driver_bridge(draft)
    assert result.passed is False
    assert "change their frozen Research-driver binding" in result.reason


def test_unsourced_dcf_anchor_requires_named_non_directional_gaps():
    draft = _draft()
    anchor = draft.assumptions[0].target_pe
    anchor.basis = "reported_fact"
    anchor.source_fact_ids = [1]

    result = _gate_evidence_binding(draft)
    assert result.passed is False
    assert "Unsourced WACC" in result.reason

    draft.gaps = [
        "WACC cost-of-capital build is unavailable; sensitivity carries uncertainty.",
        "Terminal growth is explicit judgment without a frozen macro anchor.",
    ]
    assert _gate_evidence_binding(draft).passed is True


def test_near_duplicate_vector_compares_the_entire_five_year_path():
    ours = {
        kind: tuple([100.0] * 20 + [10.0, 8.0, 9.0, 10.0, 2.0])
        for kind in ("negative", "base", "positive")
    }
    theirs = {kind: tuple(values) for kind, values in ours.items()}
    changed = list(theirs["base"])
    changed[12] = 250.0
    theirs["base"] = tuple(changed)

    assert _vectors_near_duplicate(ours, ours) is True
    assert _vectors_near_duplicate(ours, theirs) is False


def test_near_duplicate_vector_includes_every_forecast_economic_input():
    ours = {
        kind: _scenario_vector(_scenario(kind))
        for kind in ("negative", "base", "positive")
    }
    theirs = {
        kind: _scenario_vector(_scenario(kind))
        for kind in ("negative", "base", "positive")
    }
    changed = _scenario("base")
    for year in changed.forecast_years:
        year.depreciation_pct_revenue.value = 90.0
        year.cash_tax_rate_pct.value = 90.0
        year.net_financial_result_pct_revenue.value = -90.0
    theirs["base"] = _scenario_vector(changed)

    assert _vectors_near_duplicate(ours, theirs) is False


def test_event_scenario_is_distinct_when_only_non_recurring_impact_changes():
    base = _scenario("base")
    event = _scenario("event", event_pnl=10_000.0, event_cash=5_000.0)
    draft = _draft()
    draft.assumptions = [base, event]
    draft.codex_judgment.scenarios = [
        SimpleNamespace(kind="base", mechanism="Base operating path."),
        SimpleNamespace(kind="event", mechanism="A discrete non-recurring event."),
    ]

    assert _gate_scenario_distinctness(draft).passed is True


def test_method_reconciliation_rejects_unavailable_primary():
    draft = _draft()
    draft.deterministic_outputs = {
        "scenarios": [
            {
                "kind": scenario.kind,
                "methods": {
                    "fcff_dcf": {"status": "unavailable"},
                    "pe": {"status": "calculated"},
                    "ev_ebitda": {"status": "calculated"},
                },
                "method_dispersion_pct": 10,
            }
            for scenario in draft.assumptions
        ]
    }
    result = _gate_method_reconciliation(draft)
    assert result.passed is False
    assert "Primary method is unavailable" in result.reason


def test_method_reconciliation_rejects_unexplained_extreme_dispersion():
    draft = _draft()
    draft.deterministic_outputs = {
        "scenarios": [
            {
                "kind": scenario.kind,
                "methods": {
                    "fcff_dcf": {"status": "calculated"},
                    "pe": {"status": "calculated"},
                    "ev_ebitda": {"status": "calculated"},
                },
                "method_dispersion_pct": 70,
            }
            for scenario in draft.assumptions
        ]
    }
    result = _gate_method_reconciliation(draft)
    assert result.passed is False
    assert "disagree" in result.reason


def test_zero_distress_floor_does_not_bypass_method_dispersion():
    raw = _scenario("negative").model_dump(mode="json")
    raw["target_net_debt_pln_thousands"]["value"] = 300_000
    raw["cumulative_capital_allocation_pln_thousands"]["value"] += 280_000
    scenario = ValuationScenarioAssumptions.model_validate(raw)
    methodology = _methodology("ev_ebitda")
    outputs = calculate_valuation(
        {
            "company": {
                "shares_outstanding": 1_000_000,
                "market_cap_pln": 120_000_000,
                "enterprise_value_pln": 140_000_000,
                "net_debt_pln": 20_000_000,
            },
            "price": {"close_pln": 120.0},
            "street_expectations": {},
        },
        [scenario],
        methodology,
    )
    draft = SimpleNamespace(
        assumptions=[scenario],
        methodology=methodology,
        deterministic_outputs=outputs,
    )

    assert outputs["scenarios"][0]["methods"]["ev_ebitda"]["price_pln"] == 0
    assert outputs["scenarios"][0]["method_dispersion_pct"] == 100
    assert outputs["scenarios"][0]["driver_to_value_bridge"][
        "annualized_price_repricing_pct"
    ] == -100
    result = _gate_method_reconciliation(draft)
    assert result.passed is False
    assert "disagree" in result.reason

    low_primary_raw = _scenario("negative").model_dump(mode="json")
    low_primary_raw["target_pe"]["value"] = 6.0
    low_primary = ValuationScenarioAssumptions.model_validate(low_primary_raw)
    pe_methodology = _methodology("pe")
    pe_outputs = calculate_valuation(
        {
            "company": {
                "shares_outstanding": 1_000_000,
                "market_cap_pln": 120_000_000,
                "enterprise_value_pln": 140_000_000,
                "net_debt_pln": 20_000_000,
            },
            "price": {"close_pln": 120.0},
            "street_expectations": {},
        },
        [low_primary],
        pe_methodology,
    )
    pe_draft = SimpleNamespace(
        assumptions=[low_primary],
        methodology=pe_methodology,
        deterministic_outputs=pe_outputs,
    )
    assert pe_outputs["scenarios"][0]["method_dispersion_pct"] == 84.33
    assert _gate_method_reconciliation(pe_draft).passed is False
