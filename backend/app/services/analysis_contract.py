"""Provider-neutral analysis output contract checks.

Skills guide Codex behavior, but mutating save paths need a small deterministic
guard too. A quick/deep analysis may be saved as rejected or draft with partial
fields, but `verification_status=pass` must mean the result is scoreable and
the result-quality verifier has something concrete to audit.
"""
from __future__ import annotations

from typing import Any

from app.services import analysis_scoring, scenarios

ANALYSIS_WORKFLOWS_REQUIRING_PREDICTION = {
    "stock-quick-analysis",
    "stock-deep-analysis",
}
VALID_PREDICTION_DIRECTIONS = {"positive", "neutral", "negative"}
VALID_SCENARIO_VALIDITY = {"valid", "limited", "invalid"}
LEGACY_OUTPUT_CONTRACT_VERSION = "legacy"
SCORED_SCENARIO_OUTPUT_CONTRACT_VERSION = "scored-scenario-v1"
SCENARIO_SIMULATION_WORKFLOW = "scenario-simulation"
SCENARIO_VERIFIER_CHECKS = (
    "representative_archetypes",
    "no_lookahead",
    "math_reconciliation",
    "source_lineage",
    "scenario_input_match",
)


def output_contract_version(output: dict[str, Any]) -> str:
    """Return the persisted output shape without inferring new semantics.

    SJ.0 introduces the version marker only. Later scored-judgment slices will
    require and validate the new fields; old analyses remain readable as
    ``legacy`` so their historical result is not rewritten or reinterpreted.
    """
    version = output.get("analysis_contract_version")
    if version == SCORED_SCENARIO_OUTPUT_CONTRACT_VERSION:
        return version
    return LEGACY_OUTPUT_CONTRACT_VERSION


def verified_analysis_contract_errors(
    *,
    workflow: str,
    verification_status: str,
    output: dict[str, Any],
    input_snapshot: dict[str, Any] | None = None,
) -> list[str]:
    """Return deterministic contract errors for approved Codex analyses."""
    if workflow not in ANALYSIS_WORKFLOWS_REQUIRING_PREDICTION:
        return []
    if verification_status.lower() != "pass":
        return []

    errors: list[str] = []
    prediction = output.get("prediction")
    if not isinstance(prediction, dict):
        errors.append("output.prediction is required for verified company analysis.")
    else:
        direction = prediction.get("direction")
        if direction not in VALID_PREDICTION_DIRECTIONS:
            errors.append(
                "output.prediction.direction must be positive, neutral, or negative."
            )
        horizon = prediction.get("horizon_days")
        if not isinstance(horizon, int) or horizon <= 0:
            errors.append("output.prediction.horizon_days must be a positive integer.")
        source_fields = prediction.get("source_fields")
        if not _nonempty_string_list(source_fields):
            errors.append("output.prediction.source_fields must be a non-empty string list.")

    potential = output.get("potential")
    if not isinstance(potential, dict):
        errors.append("output.potential is required for verified company analysis.")
    else:
        if not _number(potential.get("value_pct")):
            errors.append("output.potential.value_pct must be numeric.")
        source = potential.get("source")
        if not isinstance(source, str) or not source.strip():
            errors.append("output.potential.source must name the deterministic source field.")

    result_quality = output.get("result_quality")
    if not isinstance(result_quality, dict):
        errors.append("output.result_quality is required for verified company analysis.")
    else:
        if not isinstance(result_quality.get("result_cause"), str) or not result_quality[
            "result_cause"
        ].strip():
            errors.append("output.result_quality.result_cause must be a non-empty string.")
        if not isinstance(result_quality.get("one_off_risk"), str) or not result_quality[
            "one_off_risk"
        ].strip():
            errors.append("output.result_quality.one_off_risk must be a non-empty string.")
        validity = result_quality.get("scenario_validity")
        if validity not in VALID_SCENARIO_VALIDITY:
            errors.append(
                "output.result_quality.scenario_validity must be valid, limited, or invalid."
            )
        warnings = result_quality.get("scenario_warnings")
        if warnings is not None and not _string_list(warnings):
            errors.append("output.result_quality.scenario_warnings must be a string list.")

    if output_contract_version(output) == SCORED_SCENARIO_OUTPUT_CONTRACT_VERSION:
        errors.extend(_scored_scenario_probability_errors(output))
        errors.extend(_scored_scenario_impact_errors(output, input_snapshot or {}))
        errors.extend(_conviction_score_errors(output, input_snapshot or {}))
        delivery = output.get("delivery")
        if not isinstance(delivery, dict) or delivery.get("status") not in {"verified", "provisional"} or not _string_list(delivery.get("data_gaps")):
            errors.append("output.delivery requires status verified/provisional and explicit data_gaps.")

    return errors


def _conviction_score_errors(output: dict[str, Any], input_snapshot: dict[str, Any]) -> list[str]:
    base = input_snapshot.get("codex_score_base")
    actual = output.get("conviction_score")
    if not isinstance(base, dict) or not isinstance(actual, dict):
        return ["input_snapshot.codex_score_base and output.conviction_score are required for verified scored analysis."]
    expected = analysis_scoring.compute_conviction_score(base, output.get("scenario_outcomes") or [])
    if actual != expected:
        return ["output.conviction_score must match the frozen score base and deterministic scenario impacts."]
    return []


def _scored_scenario_impact_errors(output: dict[str, Any], input_snapshot: dict[str, Any]) -> list[str]:
    scenario_set = input_snapshot.get("scenario_set")
    if not isinstance(scenario_set, dict):
        return ["input_snapshot.scenario_set is required for verified scored scenario impacts."]
    fingerprint = scenarios.scenario_set_fingerprint(scenario_set)
    if output.get("scenario_set_fingerprint") != fingerprint:
        return ["output.scenario_set_fingerprint must match input_snapshot.scenario_set."]
    errors: list[str] = []
    for index, outcome in enumerate(output.get("scenario_outcomes", [])):
        if not isinstance(outcome, dict):
            continue
        expected = scenarios.deterministic_impact(scenario_set, outcome.get("scenario_set_id"))
        actual = outcome.get("deterministic_impact")
        if actual != expected:
            errors.append(f"output.scenario_outcomes[{index}].deterministic_impact must match the frozen scenario_set.")
    return errors


def _scored_scenario_probability_errors(output: dict[str, Any]) -> list[str]:
    """Validate the SJ.1 probability/provenance slice of a scored analysis.

    The later valuation slice owns numeric marker and price projections.  This
    slice only makes the mutually-exclusive scenario probabilities auditable:
    each scenario must say what evidence supports it or name an explicit gap.
    """
    errors: list[str] = []
    outcomes = output.get("scenario_outcomes")
    if not isinstance(outcomes, list) or len(outcomes) < 3:
        return ["output.scenario_outcomes must contain at least negative, base and positive outcomes."]

    ids: set[str] = set()
    kinds: set[str] = set()
    probability_total = 0.0
    for index, outcome in enumerate(outcomes):
        path = f"output.scenario_outcomes[{index}]"
        if not isinstance(outcome, dict):
            errors.append(f"{path} must be an object.")
            continue
        outcome_id = outcome.get("id")
        if not isinstance(outcome_id, str) or not outcome_id.strip():
            errors.append(f"{path}.id must be a non-empty string.")
        elif outcome_id in ids:
            errors.append(f"{path}.id must be unique.")
        else:
            ids.add(outcome_id)
        kind = outcome.get("kind")
        if kind not in {"negative", "base", "positive", "event"}:
            errors.append(f"{path}.kind must be negative, base, positive, or event.")
        else:
            kinds.add(kind)
        probability = outcome.get("probability_pct")
        if not _number(probability) or probability < 0 or probability > 100:
            errors.append(f"{path}.probability_pct must be a number from 0 to 100.")
        else:
            probability_total += float(probability)
        _provenance_errors(errors, path, "drivers", outcome.get("drivers"))
        _provenance_errors(errors, path, "assumptions", outcome.get("assumptions"))

    if not {"negative", "base", "positive"}.issubset(kinds):
        errors.append("output.scenario_outcomes must include negative, base and positive outcomes.")
    if probability_total and not 99.5 <= probability_total <= 100.5:
        errors.append("output.scenario_outcomes probability_pct values must sum to approximately 100.")
    return errors


def _provenance_errors(errors: list[str], path: str, field: str, value: Any) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{path}.{field} must be a non-empty provenance list.")
        return
    for index, entry in enumerate(value):
        item_path = f"{path}.{field}[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{item_path} must be an object with source_ids or gap.")
            continue
        source_ids = entry.get("source_ids")
        gap = entry.get("gap")
        has_sources = _nonempty_string_list(source_ids)
        has_gap = isinstance(gap, str) and bool(gap.strip())
        if not has_sources and not has_gap:
            errors.append(f"{item_path} must include non-empty source_ids or an explicit gap.")


def verified_scenario_simulation_contract_errors(
    *,
    workflow: str,
    verification_status: str,
    input_snapshot: dict[str, Any],
    output: dict[str, Any],
    verification: dict[str, Any],
) -> list[str]:
    """Guard approval of priced scenario simulations.

    ``math_passed`` is deliberately not enough for a saved ``pass``. The
    approval record must carry the exact deterministic scenario snapshot, the
    bridge fingerprint that was checked, and an independent strict-verifier
    result. Drafts and ``needs-human`` results remain available for audit.
    """
    if workflow != SCENARIO_SIMULATION_WORKFLOW:
        return []
    if verification_status.lower() != "pass":
        return []

    errors: list[str] = []
    scenario_set = output.get("scenario_set")
    if not isinstance(scenario_set, dict):
        errors.append("output.scenario_set is required for verified scenario simulation.")
    else:
        deterministic = scenarios.verify_scenario_simulation(scenario_set)
        if deterministic.get("status") != "math_passed":
            errors.append(
                "output.scenario_set must pass the deterministic simulation verifier."
            )
        snapshot_scenario_set = input_snapshot.get("scenario_set")
        if snapshot_scenario_set != scenario_set:
            errors.append(
                "input_snapshot.scenario_set must match the saved deterministic scenario set."
            )
        simulation_verification = scenario_set.get("simulation_verification")
        if isinstance(simulation_verification, dict) and simulation_verification.get(
            "strict_verification_required"
        ) is False:
            errors.append("output.scenario_set cannot disable strict verification.")

    priced_gate = output.get("priced_operating_outcomes")
    if not isinstance(priced_gate, dict) or priced_gate.get("status") != "approved":
        errors.append(
            "output.priced_operating_outcomes.status must be approved for a verified scenario simulation."
        )
    bridge_fingerprint = (
        priced_gate.get("input_fingerprint") if isinstance(priced_gate, dict) else None
    )
    if not isinstance(bridge_fingerprint, str) or not bridge_fingerprint.strip():
        errors.append("Priced outcomes must expose the checked bridge input fingerprint.")
    snapshot_fingerprint = input_snapshot.get("operating_bridge_fingerprint")
    if snapshot_fingerprint != bridge_fingerprint:
        errors.append(
            "input_snapshot.operating_bridge_fingerprint must match the priced-outcome fingerprint."
        )

    if verification.get("model_role") != "verifier_strict":
        errors.append("verification.model_role must be verifier_strict.")
    if verification.get("verdict") != "pass":
        errors.append("verification.verdict must be pass.")
    verifier_model = verification.get("verifier_model")
    if not isinstance(verifier_model, str) or not verifier_model.strip():
        errors.append("verification.verifier_model must identify the strict verifier.")

    checks = verification.get("checks")
    if not isinstance(checks, dict):
        errors.append("verification.checks is required for verified scenario simulation.")
    else:
        for check_id in SCENARIO_VERIFIER_CHECKS:
            value = checks.get(check_id)
            passed = _check_pass(value)
            if check_id == "representative_archetypes" and isinstance(value, dict):
                archetypes = value.get("archetypes")
                passed = isinstance(archetypes, list) and {
                    "industrial",
                    "financial",
                    "event-driven",
                }.issubset(set(archetypes))
            if not passed:
                errors.append(f"verification.checks.{check_id} must pass.")
        input_match = checks.get("scenario_input_match")
        if isinstance(input_match, dict) and input_match.get("fingerprint") != bridge_fingerprint:
            errors.append(
                "verification.checks.scenario_input_match must carry the current bridge fingerprint."
            )

    return errors


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _nonempty_string_list(value: Any) -> bool:
    return _string_list(value) and len(value) > 0


def _check_pass(value: Any) -> bool:
    if value is True:
        return True
    if not isinstance(value, dict):
        return False
    return value.get("passed") is True or value.get("verdict") in {
        "pass",
        "passed",
        "spełnia",
    }
