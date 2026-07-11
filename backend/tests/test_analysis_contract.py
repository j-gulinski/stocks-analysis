"""Regression coverage for versioned saved-analysis output contracts."""


def test_output_contract_version_preserves_legacy_payloads():
    from app.services.analysis_contract import (
        LEGACY_OUTPUT_CONTRACT_VERSION,
        output_contract_version,
    )

    assert output_contract_version({"prediction": {"direction": "neutral"}}) == (
        LEGACY_OUTPUT_CONTRACT_VERSION
    )


def test_output_contract_version_identifies_scored_scenario_payloads():
    from app.services.analysis_contract import (
        SCORED_SCENARIO_OUTPUT_CONTRACT_VERSION,
        output_contract_version,
    )

    assert output_contract_version(
        {"analysis_contract_version": "scored-scenario-v1"}
    ) == SCORED_SCENARIO_OUTPUT_CONTRACT_VERSION


def test_mcp_persists_scored_output_contract_version(db):
    from app.db.models import AnalysisRun, Company
    from app.mcp.stock_tools import save_analysis_run

    db.add(Company(ticker="SCO", name="Scored contract fixture"))
    db.commit()

    result = save_analysis_run(
        {
            "ticker": "SCO",
            "workflow": "stock-deep-analysis",
            "model_role": "verifier_strict",
            "model": "gpt-5.6-sol",
            "verification_status": "draft",
            "output": {"analysis_contract_version": "scored-scenario-v1"},
        }
    )

    record = db.get(AnalysisRun, result["analysis_run_id"])
    assert record.output_contract_version == "scored-scenario-v1"


def test_mcp_dossier_exposes_codex_only_score_base(db):
    from app.db.models import Company
    from app.mcp.stock_tools import get_company_dossier

    db.add(Company(ticker="BASE", name="Score base fixture"))
    db.commit()

    result = get_company_dossier({"ticker": "BASE"})

    assert "workbench_score" not in result["dossier"]
    assert result["codex_score_base"]["version"] == "codex-score-base-v1"
    assert result["codex_score_base"]["factors"][0]["weight"] == 30
    assert result["codex_score_base"]["deterministic_signal"] is None


def _verified_scored_output() -> dict:
    provenance = [{"source_ids": ["document-version:42"]}]
    scenario_set = {"current_price": 10.0, "scenarios": [
        {"id": "negative", "target_multiple": {"type": "cz", "value": 8.0}, "target_price": 8.0, "implied_upside_pct": -20.0},
        {"id": "base", "target_multiple": {"type": "cz", "value": 10.0}, "target_price": 10.0, "implied_upside_pct": 0.0},
        {"id": "positive", "target_multiple": {"type": "cz", "value": 12.0}, "target_price": 12.0, "implied_upside_pct": 20.0},
    ]}
    from app.services import scenarios
    output = {
        "analysis_contract_version": "scored-scenario-v1",
        "prediction": {"direction": "neutral", "horizon_days": 90, "source_fields": ["quarters"]},
        "potential": {"value_pct": 12.0, "source": "valuation.potential.value_pct"},
        "result_quality": {"result_cause": "operating", "one_off_risk": "low", "scenario_validity": "valid"},
        "scenario_outcomes": [
            {"id": "bear", "kind": "negative", "probability_pct": 25, "scenario_set_id": "negative", "drivers": provenance, "assumptions": provenance},
            {"id": "base", "kind": "base", "probability_pct": 50, "scenario_set_id": "base", "drivers": provenance, "assumptions": provenance},
            {"id": "bull", "kind": "positive", "probability_pct": 25, "scenario_set_id": "positive", "drivers": provenance, "assumptions": provenance},
        ],
    }
    output["scenario_set_fingerprint"] = scenarios.scenario_set_fingerprint(scenario_set)
    for row in output["scenario_outcomes"]:
        row["deterministic_impact"] = scenarios.deterministic_impact(scenario_set, row["scenario_set_id"])
    snapshot = {"scenario_set": scenario_set, "codex_score_base": {"deterministic_signal": 70, "evidence_coverage_pct": 100, "caps": []}}
    from app.services import analysis_scoring
    output["conviction_score"] = analysis_scoring.compute_conviction_score(snapshot["codex_score_base"], output["scenario_outcomes"])
    output["delivery"] = {"status": "provisional", "data_gaps": ["Operating marker bridge unavailable."]}
    return output, snapshot


def test_scored_contract_requires_normalized_probabilities_and_provenance():
    from app.services.analysis_contract import verified_analysis_contract_errors

    output, snapshot = _verified_scored_output()
    assert verified_analysis_contract_errors(
        workflow="stock-deep-analysis", verification_status="pass", output=output, input_snapshot=snapshot
    ) == []

    invalid, snapshot = _verified_scored_output()
    invalid["scenario_outcomes"][2]["probability_pct"] = 40
    invalid["scenario_outcomes"][0]["drivers"] = [{"claim": "unsupported"}]
    errors = verified_analysis_contract_errors(
        workflow="stock-deep-analysis", verification_status="pass", output=invalid, input_snapshot=snapshot
    )

    assert any("sum to approximately 100" in error for error in errors)
    assert any("source_ids or an explicit gap" in error for error in errors)
