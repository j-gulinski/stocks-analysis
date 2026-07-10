---
name: stock-pre-session-brief
description: Prepare a verified pre-session agenda for watched GPW companies. Use when the user asks to prepare a stock analysis session, check watched companies before the market session, summarize fresh ESPI/EBI/forum/company changes, or run the morning/evening Codex stock workflow.
---

# Stock pre-session brief

Create a concise session agenda from durable workbench data. Do not treat chat
memory as source data. Read from the app database/API/scripts, verify material
items, and save only structured results.

## Model routing

- Use `orchestrator` to plan the run and merge the agenda.
- Use `worker_standard` for bounded source-delta triage and formatting.
- Use `verifier_strict` for any item marked material or intended for UI display.
- Escalate to `analyst_deep` only when a fresh event can change an investment
  thesis and the dossier is already gathered.

## Procedure

1. Identify scope:
   - Default to watchlist companies.
   - If the user names tickers, limit the run to those tickers.
2. Get current data:
   - For scheduled before-session runs, prefer MCP `prepare_pre_session_brief`
     or `backend/scripts/codex_pre_session.py`; it fetches ESPI/EBI and queues
     this GPT/Codex brief workflow.
   - For manual runs, prefer MCP `get_watchlist`, `poll_espi_watchlist`, and
     `get_recent_source_deltas`.
   - Use MCP `get_company_dossier` when a company needs context.
   - If MCP is unavailable, fall back to `backend/scripts/codex_poll_espi.py
     --ticker TICKER` and `backend/scripts/codex_get_dossier.py TICKER`.
   - Do not scrape directly from a skill prompt.
3. Build a draft agenda:
   - New reports or source deltas.
   - Companies needing refresh or human review.
   - Thesis-impact candidates.
   - Data gaps blocking analysis.
4. Verify:
   - Check every material claim against event text, dossier fields, or stored
     source metadata.
   - Label forum content as opinion unless independently confirmed.
   - Reject claims that use numbers not present in inputs.
5. Save:
   - Save company-specific analysis with MCP `save_analysis_run` when the
     output is tied to a ticker and includes verification metadata.
   - If MCP is unavailable, save company-specific analysis with
     `backend/scripts/codex_save_analysis.py` only when the output is tied to a
     ticker and includes verification metadata.

## Output contract

Return a compact agenda with:

- `workflow`: `stock-pre-session-brief`
- `scope`: tickers checked
- `new_events`: verified source changes
- `needs_human`: questions for the user
- `deep_analysis_candidates`: tickers and reasons
- `data_gaps`: missing or stale inputs
- `verification_status`: `pass`, `fail`, or `needs-human`

Keep failed or uncertain findings visible as audit notes. Do not present them as
approved analysis.
