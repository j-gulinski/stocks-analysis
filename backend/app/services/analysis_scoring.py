"""Reusable deterministic base for Codex's verified company judgment.

This is intentionally *not* a Dossier/UI rating.  It supplies a transparent
weighted base to a Codex analysis and its independent verifier; the verifier
still owns the saved conviction score after considering scenario probabilities,
primary evidence and explicitly recorded gaps.
"""

from __future__ import annotations

import math


SCORE_BASE_VERSION = "codex-score-base-v1"

# Growth in revenue and profit is deliberately the largest component.  The
# qualitative rows remain unknown until the Codex research pass records durable
# evidence; neither author reputation nor company size is a factor.
FACTOR_DEFINITIONS = (
    ("growth", "Wzrost przychodów i zysków", 30, ("revenue_growth", "gross_margin_trend", "operating_leverage")),
    ("durability", "Trwałość poprawy i jakość zysku", 20, ("profit_quality",)),
    ("balance_sheet", "Bilans i gotówka", 15, ("balance_sheet",)),
    ("valuation", "Wycena względem własnej historii", 15, ("valuation_vs_history",)),
    ("catalyst_business", "Katalizator i jakość biznesu", 15, ("catalyst", "framing")),
    ("capital_allocation", "Alokacja kapitału", 5, ("dividend",)),
)

WEIGHTS = {
    check_id: weight / len(check_ids)
    for _, _, weight, check_ids in FACTOR_DEFINITIONS
    for check_id in check_ids
}

_PRESCORE_TO_SCORE_CHECK = {
    "revenue_growth": "revenue_growth",
    "gross_margin_trend": "gross_margin_trend",
    "operating_leverage": "operating_leverage",
    "profit_quality": "profit_quality",
    "net_cash": "balance_sheet",
    "pe_vs_history": "valuation_vs_history",
    "dividend": "dividend",
}


def build_codex_score_base(dossier: dict) -> dict:
    """Build the fixed evidence base which a Codex verifier must carry forward.

    ``deterministic_signal`` is a partial read of statement-derived fields, not
    an investable recommendation or the final company score.  Missing catalyst
    and governance evidence stays visible as an unknown, rather than being
    silently scored by Python.
    """
    prescore_checks = {
        _PRESCORE_TO_SCORE_CHECK[item["id"]]: item
        for item in (dossier.get("prescore") or {}).get("checks", [])
        if item.get("id") in _PRESCORE_TO_SCORE_CHECK
    }

    factors: list[dict] = []
    earned = 0.0
    known_weight = 0.0
    for factor_id, label, weight, check_ids in FACTOR_DEFINITIONS:
        available = [
            prescore_checks[check_id]
            for check_id in check_ids
            if check_id in prescore_checks
            and prescore_checks[check_id].get("verdict") != "unknown"
        ]
        if not available:
            factors.append(
                {
                    "id": factor_id,
                    "label": label,
                    "weight": weight,
                    "status": "unknown",
                    "earned": None,
                    "source": "Codex research required" if factor_id == "catalyst_business" else "deterministic dossier gap",
                }
            )
            continue
        fraction = sum(item.get("verdict") == "pass" for item in available) / len(available)
        points = weight * fraction
        earned += points
        known_weight += weight
        factors.append(
            {
                "id": factor_id,
                "label": label,
                "weight": weight,
                "status": "pass" if fraction == 1 else "fail",
                "earned": round(points, 1),
                "source": "deterministic dossier",
            }
        )

    ttm = dossier.get("ttm") or {}
    net_cash = (dossier.get("net_cash") or {}).get("value")
    caps: list[dict] = []
    if prescore_checks.get("profit_quality", {}).get("verdict") == "fail":
        caps.append({"id": "one_off_profit", "maximum_score": 50})
    if (
        _number(ttm.get("net_profit"))
        and ttm["net_profit"] < 0
        and _number(net_cash)
        and net_cash < 0
    ):
        caps.append({"id": "loss_with_net_debt", "maximum_score": 40})

    signal = None
    if known_weight:
        signal = math.floor((100 * earned / known_weight) + 0.5)
        for cap in caps:
            signal = min(signal, cap["maximum_score"])
    return {
        "version": SCORE_BASE_VERSION,
        "purpose": "Codex/verifier input; not a standalone company rating or trade instruction.",
        "deterministic_signal": signal,
        "evidence_coverage_pct": int(known_weight),
        "factors": factors,
        "caps": caps,
        "final_score_rule": (
            "The strict verifier must derive the final conviction score from this base, "
            "source-grounded catalyst/business evidence and probability-weighted scenarios."
        ),
    }


def compute_conviction_score(score_base: dict, scenario_outcomes: list[dict]) -> dict:
    """Reproducible 1–100 score for a verifier-approved scored analysis."""
    signal, coverage = score_base.get("deterministic_signal"), score_base.get("evidence_coverage_pct")
    if not _number(signal) or not _number(coverage):
        return {"value": None, "scale": 100, "status": "provisional", "reason": "Brak policzalnej bazy dowodowej."}
    returns = []
    for outcome in scenario_outcomes:
        price = (outcome.get("deterministic_impact") or {}).get("price_impact") or {}
        if not _number(outcome.get("probability_pct")) or not _number(price.get("return_pct")):
            return {"value": None, "scale": 100, "status": "provisional", "reason": "Brak pełnego policzalnego wpływu cenowego."}
        returns.append(float(outcome["probability_pct"]) / 100 * float(price["return_pct"]))
    weighted_return = sum(returns)
    value = math.floor((0.5 * signal + 0.25 * coverage + 0.25 * min(max((weighted_return + 100) / 2, 0), 100)) + 0.5)
    for cap in score_base.get("caps", []):
        if _number(cap.get("maximum_score")): value = min(value, int(cap["maximum_score"]))
    return {"value": value, "scale": 100, "status": "provisional" if coverage < 85 else "ready_for_verifier", "basis": {"score_base": signal, "evidence_coverage_pct": coverage, "weighted_return_pct": round(weighted_return, 2)}}


def compute_alignment_score(verdict: dict, dossier: dict) -> int | None:
    """Legacy direct-provider compatibility using the current score weights.

    New manual Codex flows receive :func:`build_codex_score_base` and persist a
    verifier-owned score instead.  Keeping this function pure avoids two
    competing rating definitions during the provider-sunset transition.
    """
    by_id: dict[str, dict] = {}
    for item in verdict.get("checklist", []):
        item_id = item.get("id")
        if item_id not in WEIGHTS or item.get("verdict") == "nieznane":
            continue
        # The strict provider contract rejects duplicates. Keeping the scorer
        # defensive prevents accidental double weighting if a future caller
        # invokes this pure function before validation.
        by_id[item_id] = item

    known = list(by_id.values())

    # Fewer than three known items is insufficient evidence for even a partial
    # legacy score.
    if len(known) < 3:
        return None

    denominator = sum(WEIGHTS[item["id"]] for item in known)
    if denominator <= 0:
        return None
    earned = sum(
        WEIGHTS[item["id"]]
        for item in known
        if item.get("verdict") == "spełnia"
    )
    # Financial/UI scores use conventional half-up rounding; Python's built-in
    # round uses banker's rounding and would turn 62.5 into 62.
    score = math.floor((100 * earned / denominator) + 0.5)

    # Profit-quality is already computed from statement data in the prescore;
    # it is authoritative over the model's interpretation.
    prescore_profit_quality = next(
        (
            check.get("verdict")
            for check in (dossier.get("prescore") or {}).get("checks", [])
            if check.get("id") == "profit_quality"
        ),
        None,
    )
    if (
        prescore_profit_quality == "fail"
        or by_id.get("profit_quality", {}).get("verdict") == "nie spełnia"
    ):
        score = min(score, 50)

    # Balance-sheet veto is deterministic from dossier facts: loss + net debt.
    ttm_profit = (dossier.get("ttm") or {}).get("net_profit")
    net_cash = (dossier.get("net_cash") or {}).get("value")
    if (
        isinstance(ttm_profit, (int, float))
        and isinstance(net_cash, (int, float))
        and ttm_profit < 0
        and net_cash < 0
    ):
        score = min(score, 40)

    # A missing or failed catalyst can never produce a strong-fit score.
    if by_id.get("catalyst", {}).get("verdict") != "spełnia":
        score = min(score, 75)

    return score


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
