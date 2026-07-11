---
name: stock-verifier
description: Strictly verify Stock Analysis Workbench outputs before they are marked approved. Use when checking quick analysis, deep analysis, candidate scout, pre-session brief, or backtest review results for source grounding, schema completeness, model-role discipline, and look-ahead bias.
---

# Stock verifier

Act as `verifier_strict`. Prefer false negatives over approving an unsupported
claim. Verification is about whether a result may be shown as approved in the
UI, not whether the prose sounds plausible.

## Inputs to require

- Workflow name and model role used.
- Input snapshot or dossier/event/backtest payload.
- Draft output.
- Claimed verification status.
- Any retry/escalation notes.

If inputs are missing, return `needs-human` or `fail`; do not infer.

## Checks

1. Source grounding:
   - Every numeric claim must exist in the input snapshot.
   - Every material event claim must cite an event report or stored source.
   - Forum claims must remain labelled as opinion unless independently
     confirmed.
   - A forum contributor's reported performance may prioritize which tactic to
     inspect, but it must not raise factual confidence, prediction confidence
     or the company score. Any reliability claim needs a dated track-record
     manifest with cash-flow method, total-return benchmark and evidence gaps.
2. Schema completeness:
   - Required fields for the workflow are present.
   - Missing data is explicit in `data_gaps`, `missing_data`, or equivalent.
   - Quick/deep company analysis with `verification_status=pass` includes
     `prediction`, `potential`, `result_quality`, `research_resolution`, and a
     verifier-owned `company_score` basis. When a `codex_score_base` was
     supplied, its frozen factors/caps remain in the input snapshot and the
     final basis explains the permitted scenario/evidence adjustments.
   - `stock-result-verifier` passed for quick/deep company analysis, or its
     failed checks are included and the result is saved as rejected.
   - A `scored-scenario-v1` analysis contains negative/base/positive outcomes
     whose probabilities sum to approximately 100, with driver and assumption
     provenance (`source_ids`) or an explicit evidence gap for each outcome.
3. Role discipline:
   - Routine extraction/ranking used `worker_standard`.
   - Deep synthesis used `analyst_deep` only after inputs were gathered.
   - UI-visible approval used `verifier_strict`.
4. Investment safety:
   - No direct buy/sell command.
   - Confidence reflects data quality.
   - Red flags and invalidation conditions are not hidden.
   - Downside-only scenario sets are not described with bullish wording.
   - Market-cap sweet-spot fit is not presented as a company risk unless a
     distinct sourced liquidity or market-structure risk exists.
   - Catalyst, backlog and governance fields contain researched outcomes, not
     generic instructions that push the work back to the user.
5. Backtest integrity, when applicable:
   - No future data in `known_inputs`.
   - Date boundaries and outcome windows are explicit.
   - Model interpretation is separated from deterministic math.

## Verdicts

- `pass`: output is source-grounded, complete enough, and safe to show as
  verified.
- `fail`: output has unsupported claims, wrong schema, look-ahead bias, or
  hidden uncertainty.
- `needs-human`: source access, governance judgment, or data freshness blocks a
  safe automated decision.

## Output contract

Return:

- `verdict`
- `failed_checks`
- `unsupported_claims`
- `required_fixes`
- `human_questions`
- `summary`

Use short, concrete reasons. A failed result can still be saved as an audit row,
but never as approved analysis.

When saving verifier output, prefer MCP `mark_verification_result`. If MCP is
unavailable, include the verification object in `codex_save_analysis.py` input
or report the verifier JSON in chat for manual persistence.
