---
name: workbench-run-queue
description: Process exactly one explicitly queued Stock Analysis Workbench task, then stop. Use when the user invokes $workbench-run-queue, asks Codex to run the next queued Workbench research item, or wants to turn an app-scheduled initial research request into a saved verifier-gated result. Never create, enable, or rely on a recurring automation.
---

# Run Workbench queue

Process one row only. The app owns scheduling; this skill owns the user-triggered
Codex execution boundary.

1. Run `./workbench doctor`; report and stop if unhealthy.
2. Read `docs/project-guardrails.md`, then recover expired leases and claim one
   row atomically:

   ```bash
   cd backend
   python3 scripts/codex_recover_agent_runs.py --pretty
   python3 scripts/codex_pick_agent_run.py --claim --pretty
   ```

3. Stop successfully if the queue is empty. Do not poll sources or make up work.
4. Future-dated review rows are intentionally invisible until their
   `available_at` timestamp. This is a database schedule, not an automation;
   the skill never waits, polls or claims it early. Follow the claimed
   `execution_contract` and its named skill/model. For an
   `stock-initial-research` row, first run the normal bounded company refresh,
   then create the requested company research/analysis row from the refreshed
   evidence; do not add it to the watchlist or make a trade decision.
5. Heartbeat during long work. Run the independent strict verifier required by
   the row before saving any UI-visible investment result.
6. Save/complete the same `agent_run_id`, preserve evidence and gaps, and stop.
