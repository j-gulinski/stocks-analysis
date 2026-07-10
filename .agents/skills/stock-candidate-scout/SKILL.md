---
name: stock-candidate-scout
description: Find and verify potential GPW watchlist candidates from stored companies or user-provided ticker lists. Use when the user asks to find candidates, scan for interesting stocks, shortlist companies, or discover next analysis targets.
---

# Stock candidate scout

Find candidates conservatively. A candidate is "interesting for review", not
actionable. Do not broad-crawl websites from the skill prompt.

## Model routing

- Use `worker_standard` for deterministic prescreen summaries and first ranking.
- Use a stronger model for `worker_standard` if reasons require judgment across
  several signals.
- Use `verifier_strict` on the shortlist and every promoted candidate.
- Use `analyst_deep` only for candidates close to watchlist promotion.

## Procedure

1. Determine source:
   - Default to stored companies in the database.
   - If the user supplies tickers or an export, scan only that set.
2. Run the local contract:
   - Prefer MCP `rank_candidates`.
   - If MCP is unavailable, run `cd backend && python3 scripts/codex_candidate_scan.py`.
   - Use `ticker` / `--ticker TICKER` for a narrow check.
   - Use `limit` / `--limit N` when the user wants a smaller shortlist.
3. Rank candidates:
   - Separate deterministic score from model judgment.
   - Prefer transparent reasons: valuation vs own history, net cash, growth
     signals, profit quality, source freshness.
   - Penalize stale or missing data instead of guessing.
4. Verify:
   - Check top candidates against their dossiers before recommending watchlist
     promotion.
   - Reject reasons that require unavailable data.
5. Save or report:
   - Use MCP `queue_agent_run`, `save_analysis_run`, or later `candidate_run`
     tools when persistence is needed.
   - Otherwise, report JSON-like results in chat and save company-specific
     analysis only when tied to a ticker and verified.

## Output contract

Return:

- `workflow`: `stock-candidate-scout`
- `source`
- `candidates`: ticker, score, reasons, missing_data, recommended_next_step
- `rejected`: ticker and reason when relevant
- `verification_status`

Do not add to watchlist without explicit user approval.
