---
name: stock-quick-analysis
description: Create a compact verifier-gated company analysis from the Stock Analysis Workbench dossier. Use when the user asks to quick analyze a ticker, get a first read, summarize a refreshed company, or produce a short Codex-visible analysis for the UI.
---

# Stock quick analysis

Produce a short, source-grounded company read. The goal is precision, not speed:
use a bounded worker pass, verify it, then save a structured result.

## Model routing

- Start with `worker_standard`.
- Use `verifier_strict` before any result is marked `verified`.
- Retry once with `worker_standard` after verifier feedback.
- Escalate to `analyst_deep` only if verification fails twice or the user asks
  for deeper synthesis.

## Procedure

1. Normalize the ticker to uppercase.
2. Load the dossier:
   - Prefer MCP `get_company_dossier`.
   - If MCP is unavailable, run `cd backend && python3 scripts/codex_get_dossier.py TICKER`.
   - Keep the returned top-level `codex_score_base` with the frozen
     `input_snapshot`. It is the Workbench's transparent weighting base for
     this analysis only, not a standalone Dossier/UI rating or trade signal.
   - If the script says the company is unknown or stale, tell the user what must
     be refreshed instead of inventing data.
3. Draft the quick read using only the dossier and stored event reports:
   - thesis
   - watch items
   - red flags
   - data gaps
   - next action
   - confidence
   - prediction
   - potential
   - result_quality
4. Run `stock-result-verifier` as a correction loop:
   - Compare the draft with dossier result causes, one-off risk, scenarios and
     valuation potential.
   - If it returns `fail`, revise the failed fields once and run it again.
   - If it still fails, save a rejected audit row or escalate to
     `analyst_deep`; do not mark the output verified.
5. Apply the general verifier checklist from `stock-verifier`:
   - All numbers must appear in the input snapshot.
   - Forum claims must be labelled as unverified opinion.
   - Missing data must be explicit.
   - No buy/sell advice.
6. Persist only after verification:
   - Prefer MCP `save_analysis_run`.
   - If MCP is unavailable, use `cd backend && python3 scripts/codex_save_analysis.py TICKER --workflow stock-quick-analysis --model-role ROLE --model MODEL --verification-status STATUS`.
   - Pass JSON on stdin or `--input`; include `input_snapshot`, `output`, and
     `verification`.

## Output contract

The saved `output` object must contain:

- `summary_pl`
- `thesis`
- `watch_items`
- `red_flags`
- `data_gaps`
- `next_action`
- `confidence`
- `company_score` / `alignment_score` when supported by inputs. The strict
  verifier owns its final value and explains how the frozen `codex_score_base`,
  research evidence and scenario upside/downside were combined.
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

Use `verification_status=pass` only when `stock-verifier` passes.
