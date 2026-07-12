"""Executable model routing guidance for Codex-supervised workflows.

The app cannot see the concrete model behind the current Codex host. This
module records the requested public model slug and reasoning guidance without
making a provider call. The worker still records the concrete host model when
it is known.
"""

from __future__ import annotations

from typing import Any


_POLICIES: dict[str, dict[str, Any]] = {
    "stock-initial-research": {
        "draft_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high for bounded source collection and company-specific structuring",
        "verification_scope": (
            "company identity, source freshness, tailored research structure, "
            "claim grounding and explicit gaps"
        ),
    },
    "stock-company-review": {
        "draft_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high for bounded source refresh and point-in-time company-memory comparison",
        "verification_scope": (
            "company identity, source freshness, prior-snapshot binding, claim grounding, "
            "history delta and explicit gaps"
        ),
    },
    "stock-pre-session-brief": {
        "draft_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high for material event interpretation; mechanical classification first",
        "verification_scope": "material UI-visible claims and source chronology",
    },
    "stock-quick-analysis": {
        "draft_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "prediction, potential, result quality and source grounding",
    },
    "stock-deep-analysis": {
        "draft_role": "analyst_deep",
        "draft_model": "gpt-5.6-sol",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "cross-source thesis, scenarios, valuation and look-ahead",
    },
    "stock-thesis-review": {
        "draft_role": "analyst_deep",
        "draft_model": "gpt-5.6-sol",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high for thesis delta and point-in-time comparison",
        "verification_scope": "new primary evidence, prior thesis/journal comparison and scenario updates",
    },
    "stock-candidate-scout": {
        "draft_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high for bounded synthesis; deterministic ranking first",
        "verification_scope": "stored-source grounding and candidate readiness",
    },
    "stock-backtest-review": {
        "draft_role": "analyst_deep",
        "draft_model": "gpt-5.6-sol",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "point-in-time inputs, outcome windows and calibration limits",
    },
    "stock-verifier": {
        "draft_role": "verifier_strict",
        "draft_model": "gpt-5.6-sol",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "reasoning": "high",
        "verification_scope": "independent source, schema, math and look-ahead audit",
    },
    "scenario-simulation": {
        "draft_role": "analyst_deep",
        "draft_model": "gpt-5.6-sol",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
        "reasoning": "high",
        "verification_scope": "deterministic simulation, bridge fingerprint and priced gate",
    },
    "stock-company-valuation": {
        "draft_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
        "reasoning": "Terra high for ordinary method-specific synthesis; escalate explicitly only on evidence",
        "verification_scope": (
            "research/source binding, deterministic quarter/year math, method integrity, "
            "look-ahead and final probability coherence"
        ),
    },
    "stock-portfolio-review": {
        "draft_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
        "reasoning": "Terra high for bounded interpretation of frozen deterministic portfolio analytics",
        "verification_scope": (
            "snapshot and mapping identity, reconciliation, method labels, eligible valuation "
            "arithmetic, look-ahead, exact draft and absence of transaction advice"
        ),
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
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
        "sol_ultra_default": False,
    }


def default_model_for_workflow(workflow: str) -> str:
    """Return an executable 5.6 model slug; user choice still overrides it."""
    policy = _POLICIES.get(workflow)
    if policy is None:
        return "gpt-5.6-terra"
    return str(policy["draft_model"])
