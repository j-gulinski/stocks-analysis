"""Deterministic Malik-rubric score for a validated AI checklist.

The model supplies evidence-linked verdicts; this module owns arithmetic and
vetoes. Unknown items leave the denominator exactly as `skill/rubric.md`
requires. This is pure so it can be calibrated and backtested independently.
"""

from __future__ import annotations

import math


WEIGHTS = {
    "revenue_growth": 12,
    "gross_margin_trend": 15,
    "operating_leverage": 12,
    "profit_quality": 12,
    "valuation_vs_history": 15,
    "catalyst": 10,
    "margin_of_safety": 8,
    "small_cap": 6,
    "balance_sheet": 6,
    "dividend": 2,
    "framing": 2,
}


def compute_alignment_score(verdict: dict, dossier: dict) -> int | None:
    """Compute 0–100 from known checklist items, then apply rubric vetoes."""
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

    # Rubric: fewer than three known key indicators is insufficient evidence.
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
