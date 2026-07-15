"""Adversarial computed-evidence tests for VISION V4/V5 valuation gates."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.schemas import ValuationProbabilityModel
from app.services.valuation_gates import (
    _gate_evidence_binding,
    _gate_method_reconciliation,
    _gate_probability_structure,
    _gate_scenario_distinctness,
    _gate_unknown_neutrality,
    _scenario_vector,
    _vectors_near_duplicate,
)
from tests.test_valuation_v3 import _methodology, _scenario


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
