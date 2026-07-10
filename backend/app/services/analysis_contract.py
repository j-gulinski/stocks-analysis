"""Provider-neutral analysis output contract checks.

Skills guide Codex behavior, but mutating save paths need a small deterministic
guard too. A quick/deep analysis may be saved as rejected or draft with partial
fields, but `verification_status=pass` must mean the result is scoreable and
the result-quality verifier has something concrete to audit.
"""
from __future__ import annotations

from typing import Any

ANALYSIS_WORKFLOWS_REQUIRING_PREDICTION = {
    "stock-quick-analysis",
    "stock-deep-analysis",
}
VALID_PREDICTION_DIRECTIONS = {"positive", "neutral", "negative"}
VALID_SCENARIO_VALIDITY = {"valid", "limited", "invalid"}


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


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _nonempty_string_list(value: Any) -> bool:
    return _string_list(value) and len(value) > 0
