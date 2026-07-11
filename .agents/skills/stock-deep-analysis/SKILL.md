---
name: stock-deep-analysis
description: Build a verifier-gated investment memo for a GPW company from dossier, events, thesis, scenarios, forum context, and backtest evidence. Use when the user asks for deep analysis, extraordinary analysis, decision memo, or full Codex stock review.
---

# Stock deep analysis

Build a decision-quality memo without making Codex reasoning the source of
truth. Gather inputs first, split work by risk, merge, verify, and save a
structured result for the UI.

## Model routing

- Use `gpt-5.6-terra` at high reasoning as the default research and drafting
  model. It may act as `orchestrator`, `worker_standard`, and `analyst_deep`
  while gathering sources, resolving event context, formatting evidence, and
  synthesizing the draft memo. Reserve `gpt-5.3-codex-spark` for purely
  mechanical bounded sub-loops only.
- Let the Terra worker iterate until every material question is sourced or
  explicitly recorded as a gap. Stop repeating searches that add no new
  primary evidence.
- Use `gpt-5.6-sol` at high reasoning as the independent `verifier_strict`
  pass after the merged draft. The verifier reads the frozen dossier/source
  manifest independently and owns the final
  `prediction`, `confidence`, `result_quality`, and verification status.
- Never mark a Terra draft verified without that separate Sol pass.
  Record both models and roles in `input_snapshot.model_trace`.

## Procedure

1. Load the company dossier:
   - Prefer MCP `get_company_dossier`.
   - If MCP is unavailable, use `cd backend && python3 scripts/codex_get_dossier.py TICKER`.
   - Add `--use-ai-refiners` only when the user accepts model-assisted refiners
     and the local configuration supports them.
   - Freeze the returned top-level `codex_score_base` in `input_snapshot`. It
     weights growth in revenue/profit first and records deterministic gaps and
     caps; it is input to the verifier-owned final judgment, never a Dossier
     rating or a trading instruction.
2. Audit source freshness:
   - Identify stale financials, prices, forum sync, event reports, or missing
     scenario/backtest context.
   - Refresh only through app scripts/API/MCP tools, never by ad hoc scraping.
3. Run a source-completion loop with `gpt-5.6-terra` at high reasoning:
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
   - Resolve the standing strategy questions instead of returning them as
     instructions to the user. For every company, research: (a) the concrete
     catalyst, (b) backlog/order-book level and direction, and (c) management
     credibility/governance. PortalAnaliz and BiznesRadar may provide leads;
     material conclusions require stored issuer/ESPI/EBI/GPW evidence where
     available. Record `confirmed`, `partial`, or `not_found` plus sources and
     the remaining gap for each topic.
4. Merge one draft memo with explicit evidence and dates. The Terra draft may
   propose prediction/confidence fields, but they are not authoritative.
5. Run `stock-result-verifier` with `gpt-5.6-sol` at high reasoning as a
   feedback loop on the merged memo:
   - compare stated result causes, one-off risk, scenario validity and
     potential against the gathered dossier;
   - independently decide the final prediction direction, confidence and
     result-quality fields from frozen evidence and deterministic values;
   - send only failed fields back to the Terra worker for one revision;
   - escalate or save rejected if the second pass still fails.
6. Verify with `stock-verifier`, still using `gpt-5.6-sol` at high reasoning.
   This is a distinct source/schema/safety approval, not a prose polish pass.
7. Save with MCP `save_analysis_run` using workflow `stock-deep-analysis`,
   `model_role=verifier_strict`, and the final verifier model. For a verified
   scored read, include the verifier model plus passing `no_lookahead`,
   `source_lineage` and fingerprinted `scenario_input_match` checks; the save
   path records a `VerificationRun`. Alternatively save a draft first, then use
   `mark_verification_result` with the same strict evidence. Preserve the Terra
   research/draft pass and source manifest in `input_snapshot.model_trace`.
   If MCP is unavailable, fall back to `codex_save_analysis.py`. Save rejected
   drafts too when they contain useful verifier notes.

## Output contract

The saved `output` object must contain:

- `executive_read` — at most two concise sentences; conclusion first, no long
  uncertainty preamble;
- `conviction_score` — `{value, scale, basis}` recomputed from the frozen
  input by Python and approved by the verifier. It is stored only in the scored
  output; never copy it into the legacy Malik/alignment rating. Its `basis`
  says how the frozen `codex_score_base`, source-grounded
  catalyst/business evidence and probability-weighted scenarios were combined.
  Forum-author reputation and company size must not raise or lower this score
  by themselves;
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
- `research_resolution`:
  - `catalyst`, `backlog`, `management_governance`;
  - each contains `status` (`confirmed`, `partial`, or `not_found`), concise
    `finding`, `source_ids`/URLs, `as_of`, and `remaining_gap` when applicable;
  - do not repeat an already researched item as an imperative for the user;
- `confidence`
- `delivery` — `{status: verified|provisional, data_gaps: [...]}`. Source gaps
  make the complete read provisional; only integrity failures use
  `needs-human`.
- `scenario_outcomes` when `analysis_contract_version=scored-scenario-v1`:
  - negative, base and positive mutually-exclusive outcomes with
    `probability_pct` summing to approximately 100;
  - each outcome's `drivers` and `assumptions` is a non-empty list carrying
    `source_ids`, or an explicit `gap` where primary evidence is unavailable;
  - do not attach an unpriced event/catalyst to a negative/base/positive
    deterministic row. Keep it as a driver or explicit gap until an approved
    deterministic event bridge exists;
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

Company size/sweet-spot fit may be retained as strategy context. It is not a
company risk and must not appear in `risks`/`red_flags` unless a separate,
evidence-backed liquidity or market-structure risk is actually present.

The saved `verification` object must include verifier verdict, failed checks,
and any required human follow-up.
