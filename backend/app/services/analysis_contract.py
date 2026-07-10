"""Provider-neutral analysis output contract checks.

Skills guide Codex behavior, but mutating save paths need a small deterministic
guard too. A quick/deep analysis may be saved as rejected or draft with partial
fields, but `verification_status=pass` must mean the result is scoreable and
the result-quality verifier has something concrete to audit.
"""
from __future__ import annotations

from typing import Any

from app.services import scenarios

ANALYSIS_WORKFLOWS_REQUIRING_PREDICTION = {
    "stock-quick-analysis",
    "stock-deep-analysis",
}
VALID_PREDICTION_DIRECTIONS = {"positive", "neutral", "negative"}
VALID_SCENARIO_VALIDITY = {"valid", "limited", "invalid"}
SCENARIO_SIMULATION_WORKFLOW = "scenario-simulation"
SCENARIO_VERIFIER_CHECKS = (
    "representative_archetypes",
    "no_lookahead",
    "math_reconciliation",
    "source_lineage",
    "scenario_input_match",
)


def verified_analysis_contract_errors(
    *,
    workflow: str,
    verification_status: str,
    output: dict[str, Any],
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

    return errors


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
