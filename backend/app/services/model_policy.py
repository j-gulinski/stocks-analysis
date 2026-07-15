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
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
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
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
        "reasoning": "high for bounded source refresh and point-in-time company-memory comparison",
        "verification_scope": (
            "company identity, source freshness, prior-snapshot binding, claim grounding, "
            "history delta and explicit gaps"
        ),
    },
    "stock-company-valuation": {
        "draft_role": "analyst_deep",
        "draft_model": "gpt-5.6-sol",
        "draft_reasoning_effort": "high",
        "required_verifier_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
        "reasoning": (
            "Sol high: the drafter owns company-specific scenario mechanisms, "
            "assumptions and probabilities (VISION V4) — deep analysis by routing"
        ),
        "verification_scope": (
            "adversarial review of evidence fit, mechanism plausibility and "
            "probability reasonableness; structural gates are computed by the "
            "backend and are not the verifier's to attest (VISION V5)"
        ),
    },
    "stock-portfolio-review": {
        "draft_role": "worker_standard",
        "draft_model": "gpt-5.6-terra",
        "draft_reasoning_effort": "medium",
        "required_verifier_role": "verifier_strict",
        "verifier_model": "gpt-5.6-sol",
        "verifier_reasoning_effort": "high",
        "reasoning": "Terra medium for bounded interpretation of frozen deterministic portfolio analytics",
        "verification_scope": (
            "snapshot and mapping identity, reconciliation, method labels, eligible valuation "
            "arithmetic, look-ahead, exact draft and absence of transaction advice"
        ),
    },
}

CANONICAL_WORKFLOWS = frozenset(_POLICIES)


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
        "ultra_default": False,
    }


def default_model_for_workflow(workflow: str) -> str:
    """Return the configured draft model for one canonical workflow."""
    policy = _POLICIES.get(workflow)
    if policy is None:
        raise ValueError(f"Unsupported Codex workflow '{workflow}'.")
    return str(policy["draft_model"])
