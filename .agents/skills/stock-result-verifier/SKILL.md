---
name: stock-result-verifier
description: Verify a Stock Analysis Workbench company result-quality and potential read before approval. Use when checking whether a company analysis correctly explains result causes, one-off risk, scenario validity, valuation potential, prediction direction, and whether the output may be saved as verified rather than failed or needs-human.
---

# Stock result verifier

Act as `verifier_strict` for result quality and valuation potential. The normal
automated outcome is `pass` or `fail`; ordinary source or governance gaps must
produce a complete `provisional` scored read with explicit gaps. Use
`needs-human` only for an integrity/safety failure. This skill is also
the feedback loop: compare the draft with gathered evidence, produce correction
instructions, let the analysis worker revise, then verify the corrected draft.

## Inputs to require

- Company dossier plus the top-level `codex_score_base` from
  `get_company_dossier` or `codex_get_dossier.py`.
- Draft analysis output with `prediction`, `potential`, `result_quality`,
  `research_resolution`, `company_score`, `red_flags`, `data_gaps`, and
  `verify_next`/`next_action`.
- Workflow, model role, model, and intended `verification_status`.

If the dossier is missing, stale, or not source-backed, return a provisional
read with its gap named. If the draft is missing required structured fields,
return `fail`.

## Required output fields for approved analysis

For `verification_status=pass`, the draft must include:

- `prediction.direction`: `positive`, `neutral`, or `negative`.
- `prediction.horizon_days`: numeric intended horizon.
- `prediction.source_fields`: non-empty list of dossier fields used.
- `potential.value_pct`: numeric value copied from a deterministic source such
  as `dossier.valuation.potential.value_pct`, not invented by the model.
- `potential.range_pct`: copied from deterministic scenario/valuation data when
  present.
- `result_quality.result_cause`: what drove the latest result, with source
  fields or explicit gap.
- `result_quality.one_off_risk`: durability read; high or unknown one-off risk
  must appear in `red_flags` or `data_gaps`.
- `result_quality.scenario_validity`: `valid`, `limited`, or `invalid`.
- `result_quality.scenario_warnings`: copy relevant
  `dossier.scenarios.quality_warnings`.
- `research_resolution` has explicit catalyst, backlog and
  management/governance outcomes with sources or an honest `not_found` gap.
- `company_score` has a short evidence basis and is not influenced by forum
  reputation or by the strategy's market-cap sweet spot alone. Its basis must
  preserve the frozen `codex_score_base` (growth is the largest 30-point input)
  and explain any scenario/evidence adjustment; it must not present the base's
  partial deterministic signal as the final score.

## Checks

1. Result cause:
   - Distinguish revenue growth, gross margin, operating leverage, financial
     items, tax effects, and one-offs.
   - Do not call profit repeatable merely because `one_off_share_pct` is low if
     net profit, net margin, finance result, or tax line shows an unexplained
     jump. Mark as `limited` and add `verify_next`.
2. One-off risk:
   - Treat high `one_off_share_pct`, unexplained net-margin spikes, asset-sale
     style gains, or forum/source warnings as a veto on confident positive
     potential.
   - If only operating-level one-offs are known, say that net-level one-offs are
     not fully verified.
3. Scenario validity:
   - A scenario `kind=positive` does not mean positive upside. Read the actual
     `implied_upside_pct`.
   - If all scenario upsides are negative, require the analysis to say the
     upper-quartile path is still downside and block bullish wording.
   - If scenarios rely on fallback multiple or missing drivers, mark
     `scenario_validity=limited`.
4. Potential:
   - `potential.value_pct` must match a deterministic value in the dossier.
   - `prediction.direction` must be derived from that value and explained.
   - Confidence must reflect data coverage and scenario validity, not prose
     persuasiveness.
5. Safety:
   - No direct buy/sell instruction.
   - Forum claims remain labelled as opinions unless confirmed by stored
     reports.
  - Any unresolved material source gap remains visible in `delivery.data_gaps`
    and makes the complete read `provisional`; it is not a reason to suppress
    the analysis.
   - Company size/sweet-spot mismatch is strategy-fit context, not an
     investment risk. Reject drafts that list it under `risks`/`red_flags`
     without a separate sourced liquidity or market-structure issue.
6. Research completion:
   - Verify that catalyst, backlog and governance were actually searched in
     stored sources and primary disclosures; do not accept a draft that merely
     tells the user to perform those checks.
   - A searched-but-unavailable answer is valid only as `not_found` with the
     attempted source scope and remaining gap.

## Feedback loop

Run at most two correction loops before escalation:

1. Compare the draft against dossier fields:
   - `quarters`, especially revenue, gross margin, net margin,
     `one_off_share_pct`, operating profit, and net profit.
   - `prescore.checks`.
   - `thesis.entry_quality`, `thesis.verify_next`.
   - `scenarios.scenarios`, `scenarios.weighted_expected_upside_pct`,
     `scenarios.quality_warnings`.
   - `valuation.potential`, `valuation.confidence`,
     `valuation.what_would_change`.
   - `forum.intelligence` and `event_reports` when present.
2. Return concrete patch instructions in `required_fixes`:
   - fields to add,
   - wording to remove,
   - unsupported claims to replace,
   - exact deterministic values to copy.
3. The drafting worker revises only the failed fields. It must not change
   deterministic numbers.
4. Re-run this verifier on the revised draft.
5. After two failed correction loops, escalate to `analyst_deep` or save a
   rejected audit row with the verifier notes.

## Verdicts

- `pass`: structured fields complete, numbers grounded, scenario/potential
  wording matches deterministic data, and result-quality risks are surfaced.
- `fail`: missing schema, unsupported cause/potential claim, bullish wording on
  downside-only scenarios, hidden one-off risk, or invented numbers.
- `needs-human`: deterministic math, snapshot lineage, fabrication or another
  safety/integrity check cannot be resolved automatically.

## Output contract

Return:

- `verdict`
- `failed_checks`
- `unsupported_claims`
- `required_fixes`
- `scenario_warnings`
- `one_off_notes`
- `correction_loop`
- `summary`

Save the analysis as `verified` only when this verifier returns `pass`.
