---
name: workbench-actions
description: Run explicit, user-triggered Stock Analysis Workbench actions and explain the available operator flows. Use when the user asks what the app can do, wants to start or stop it, inspect readiness, refresh or review a company, queue an analysis, or manually process one queued Codex task. Never use this skill to create or enable recurring workers.
---

# Workbench actions

Treat every action as a deliberate user request. The app may perform its
one-time session hook after `./workbench start`, but no Codex automation may be
created, enabled or resumed from this skill. The user owns when a Codex analysis
is processed.

## Choose a flow

| User intent | Flow | Result |
|---|---|---|
| “Is it ready?” | Readiness | Local dependencies, service health and stored source health only. |
| “Open/start/stop it” | App lifecycle | Start, check or stop only workbench-owned local services. |
| “Refresh/review COMPANY” | Company research | Update permitted evidence, inspect the dossier/scenarios and state gaps. |
| “Search TICKER” | Initial research | Schedule one refresh-and-research row; invoke `$workbench-run-queue` to execute it. |
| “Promote this triage” | Case promotion | Explicitly create a Company + ResearchCase, queue initial research and store a future quarterly review row. |
| “Run the next queued analysis” | Manual Codex worker | Recover leases, claim exactly one row, follow its skill and save a verifier-gated result. |
| “What changed before the session?” | One-time collection | Run the existing one-time pre-session flow only when explicitly requested. |

## Readiness and lifecycle

1. Run `./workbench doctor` first. It is read-only and never prints secrets.
2. For a start/open request, run `./workbench start` (or `--open`), then
   `./workbench status`; require backend health and frontend readiness.
3. Explain that `start` may run the repository's **one-time session hook**. It
   may collect permitted ESPI/EBI evidence and create/claim one durable row,
   but it never performs the Codex analysis itself.
4. For a stop request, run `./workbench stop`; it leaves Postgres running.

## Company research and queueing

1. Use the UI or established API/MCP path. Keep all source collection inside
   existing app adapters and their politeness limits.
2. Check freshness, source failures and deterministic scenario inputs before
   interpreting results. Separate sourced facts, computed values, assumptions
   and model judgment.
   Codex dossier reads also carry a top-level `codex_score_base`: a reusable
   analysis-only weighting base (growth in revenue/profit first), not a Dossier
   card, recommendation or standalone rating. Freeze it with the analysis
   input and let the strict verifier own the final scored judgment.
   A saved scored read displays its verifier-owned conviction score, scenario
   probabilities and deterministic price outcomes in the existing analysis
   card. `provisional` means named evidence gaps, not a hidden or suppressed
   result; only integrity failures are `needs-human`.
3. A ticker search and every new top-15 Discover entry schedule an
   `stock-initial-research` `agent_run`; it is not a model call. Report its
   status as `queued`, `running`, `verified`, `rejected` or `needs-human`.
4. Do not add a ticker to the watchlist, make a trade decision or treat forum
   content as primary evidence without the user's explicit action and durable
   source evidence.
5. A promotion is a distinct click after the `promote_to_case` triage row is
   saved. It copies the immutable review price/note/evidence into the case,
   queues initial research and records a future-dated quarterly thesis-review
   row. Future rows cannot be claimed before their date and never wake Codex;
   material events require a separate explicit review action.

## Manual Codex worker

Use this flow only after the user explicitly asks to run a queued analysis.

1. Read `docs/project-guardrails.md`, `.codex/tasks/stock-queue-worker.md`
   and the skill named by the claimed row.
2. Run `./workbench doctor`; stop and report the blocker if it fails.
3. Recover expired leases, then atomically claim at most one row:

   ```bash
   cd backend
   python3 scripts/codex_recover_agent_runs.py --pretty
   python3 scripts/codex_pick_agent_run.py --claim --pretty
   ```

4. Stop successfully when the queue is empty. Do not poll sources or create
   speculative work in that case.
5. Follow the row's `execution_contract`, requested model and workflow skill.
   Keep data source-grounded, heartbeat during long work, and use an
   independent strict verifier before saving UI-visible investment output.
6. Save or complete the same `agent_run_id` through the documented MCP or
   fallback scripts. Preserve evidence, assumptions, verification status and
   explicit gaps.

## Capability-maintenance rule

When a user-facing Workbench action changes—UI control, API/MCP action,
`workbench` command, queue lifecycle or source/analysis boundary—update this
skill in the same change. Keep the flow table truthful, add the normal
`CHANGELOG.md` and `docs/model-usage.md` records, and verify the affected flow.
