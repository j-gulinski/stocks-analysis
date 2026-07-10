---
name: stock-deep-analysis
description: Build a verifier-gated investment memo for a GPW company from dossier, events, thesis, scenarios, forum context, and backtest evidence. Use when the user asks for deep analysis, extraordinary analysis, decision memo, or full Codex stock review.
---

# Stock deep analysis

Build a decision-quality memo without making Codex reasoning the source of
truth. Gather inputs first, split work by risk, merge, verify, and save a
structured result for the UI.

## Model routing

- Use `orchestrator` to plan subtasks and merge the final memo.
- Use `worker_standard` for data freshness audit, event triage, and formatting.
- Use `analyst_deep` for synthesis across fundamentals, events, scenarios,
  valuation, forum context, and backtest evidence.
- Use `verifier_strict` on the merged memo before saving as verified.

## Procedure

1. Load the company dossier:
   - Prefer MCP `get_company_dossier`.
   - If MCP is unavailable, use `cd backend && python3 scripts/codex_get_dossier.py TICKER`.
   - Add `--use-ai-refiners` only when the user accepts model-assisted refiners
     and the local configuration supports them.
2. Audit source freshness:
   - Identify stale financials, prices, forum sync, event reports, or missing
     scenario/backtest context.
   - Refresh only through app scripts/API/MCP tools, never by ad hoc scraping.
3. Split the analysis:
   - Data worker: source freshness, known gaps, event materiality.
   - Thesis worker: Malik/OBS fit using `skill/SKILL.md` and
     `docs/strategy-malik.md` if needed.
   - Scenario/backtest worker: deterministic scenario read and any available
     backtest context.
   - Risk worker: one-offs, governance gaps, liquidity, source quality.
4. Merge into one memo with explicit evidence and dates.
5. Run `stock-result-verifier` as a feedback loop on the merged memo:
   - compare stated result causes, one-off risk, scenario validity and
     potential against the gathered dossier;
   - revise failed fields once from verifier feedback;
   - escalate or save rejected if the second pass still fails.
6. Verify with `stock-verifier`.
7. Save with MCP `save_analysis_run` using workflow `stock-deep-analysis`.
   If MCP is unavailable, fall back to `codex_save_analysis.py`. Save rejected
   drafts too when they contain useful verifier notes.

## Output contract

The saved `output` object must contain:

- `executive_read`
- `thesis`
- `evidence`
- `valuation`
- `risks`
- `forum_context`
- `backtest_context`
- `action_plan`
- `confidence`
- `prediction`:
  - `direction`: `positive`, `neutral`, or `negative`
  - `horizon_days`
  - `source_fields`
- `potential`:
  - `value_pct`
  - `range_pct`
  - `source`
- `result_quality`:
  - `result_cause`
  - `one_off_risk`
  - `scenario_validity`
  - `scenario_warnings`

The saved `verification` object must include verifier verdict, failed checks,
and any required human follow-up.
