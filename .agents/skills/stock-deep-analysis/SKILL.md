---
name: stock-deep-analysis
description: Build a verifier-gated investment memo for a GPW company from dossier, events, thesis, scenarios, forum context, and backtest evidence. Use when the user asks for deep analysis, extraordinary analysis, decision memo, or full Codex stock review.
---

# Stock deep analysis

Build a decision-quality memo without making Codex reasoning the source of
truth. Gather inputs first, split work by risk, merge, verify, and save a
structured result for the UI.

## Model routing

- Use `gpt-5.3-codex-spark` as the default research and drafting model. It may
  act as `orchestrator`, `worker_standard`, and `analyst_deep` while gathering
  sources, resolving event context, formatting evidence, and synthesizing the
  draft memo.
- Let the 5.3 worker iterate until every material question is sourced or
  explicitly recorded as a gap. Stop repeating searches that add no new
  primary evidence.
- Use `verifier_strict` with the strongest configured model, currently
  `gpt-5.5` with high reasoning, after the merged draft. The verifier reads the
  frozen dossier/source manifest independently and owns the final
  `prediction`, `confidence`, `result_quality`, and verification status.
- Never mark a 5.3 draft verified without that separate strongest-model pass.
  Record both models and roles in `input_snapshot.model_trace`.

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
3. Run a source-completion loop with `gpt-5.3-codex-spark`:
   - Start from stored dossier, source documents and event reports.
   - When a material interpretation remains unexplained, browse primary
     sources in this order: issuer IR/reports, ESPI/EBI, GPW. Use secondary
     sources only as labelled discovery leads.
   - Capture a source manifest with title, URL/source id, publication date,
     `known_at` when available, access date, covered claim and persistence
     status in the workbench.
   - Ingest material official evidence through an existing app adapter when
     supported. If it cannot be persisted, keep the URL in the frozen input
     and require `needs-human`; browser context alone is not durable evidence.
   - Split the draft into data/event, thesis, scenario/backtest and risk passes.
     Re-run only a pass whose material questions remain unresolved.
   - Treat forum portfolio authors as process leads, never as primary company
     evidence. A contributor's tactics may receive higher research priority
     only when a public track-record manifest covers at least three years,
     dated cash flows, dividends/fees, a same-period total-return benchmark,
     drawdown and point-in-time publication. Reported but non-reproducible
     performance remains `needs-human` and cannot increase stock confidence.
   - Prefer reusable process rules seen in credible long-duration portfolios:
     a written pre-trade case, maximum acceptable price, explicit
     invalidation, thesis-delta after results, low-turnover patience and
     concentration review after exceptional gains. Never copy a position or
     turn author reputation into a company score.
4. Merge one draft memo with explicit evidence and dates. The 5.3 draft may
   propose prediction/confidence fields, but they are not authoritative.
5. Run `stock-result-verifier` with the strongest configured model as a
   feedback loop on the merged memo:
   - compare stated result causes, one-off risk, scenario validity and
     potential against the gathered dossier;
   - independently decide the final prediction direction, confidence and
     result-quality fields from frozen evidence and deterministic values;
   - send only failed fields back to the 5.3 worker for one revision;
   - escalate or save rejected if the second pass still fails.
6. Verify with `stock-verifier`, still using the strongest configured model.
   This is a distinct source/schema/safety approval, not a prose polish pass.
7. Save with MCP `save_analysis_run` using workflow `stock-deep-analysis`,
   `model_role=verifier_strict`, and the final verifier model. Preserve the 5.3
   research/draft pass and source manifest in `input_snapshot.model_trace`.
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
  - forum claims stay labelled as leads;
  - any contributor reliability assessment records period, return method,
    benchmark and evidence gaps, and affects research priority only;
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
