"""Provider-free routing guidance for Codex-supervised workflows.

The app cannot see the concrete model behind the current Codex host. This
module therefore returns role and reasoning guidance, not a model name or a
provider call. The worker records the concrete host model when it is known.
"""
from __future__ import annotations

from typing import Any


_POLICIES: dict[str, dict[str, Any]] = {
    "stock-pre-session-brief": {
        "draft_role": "worker_standard",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high for material event interpretation; mechanical triage first",
        "verification_scope": "material UI-visible claims and source chronology",
    },
    "stock-quick-analysis": {
        "draft_role": "analyst_deep",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "prediction, potential, result quality and source grounding",
    },
    "stock-deep-analysis": {
        "draft_role": "analyst_deep",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "cross-source thesis, scenarios, valuation and look-ahead",
    },
    "stock-candidate-scout": {
        "draft_role": "worker_standard",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high for bounded synthesis; deterministic ranking first",
        "verification_scope": "stored-source grounding and candidate readiness",
    },
    "stock-backtest-review": {
        "draft_role": "analyst_deep",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "point-in-time inputs, outcome windows and calibration limits",
    },
    "stock-verifier": {
        "draft_role": "verifier_strict",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "independent source, schema, math and look-ahead audit",
    },
    "scenario-simulation": {
        "draft_role": "analyst_deep",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "deterministic simulation, bridge fingerprint and priced gate",
    },
}


def get_model_policy(workflow: str) -> dict[str, Any]:
    """Return explicit Codex role guidance without selecting a hidden model."""
    policy = _POLICIES.get(workflow)
    if policy is None:
        return {
            "workflow": workflow,
            "status": "needs-human",
            "draft_role": None,
            "required_verifier_role": "verifier_strict",
            "reasoning": "needs-human",
            "verification_scope": "Unknown workflow; inspect the queue contract manually.",
            "provider_mode": "codex-host",
            "api_key_required": False,
            "concrete_model_source": "current Codex host; exact deployment not exposed",
        }
    return {
        "workflow": workflow,
        "status": "ready",
        **policy,
        "provider_mode": "codex-host",
        "api_key_required": False,
        "concrete_model_source": "current Codex host; exact deployment not exposed",
        "record_concrete_model": True,
        "sol_ultra_default": False,
    }
