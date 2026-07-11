---
name: workbench-run-queue
description: Execute exactly one explicitly queued Stock Analysis Workbench job and stop. Use when the user invokes $workbench-run-queue or asks Codex to run the next queued Research job. Never create, enable, or imitate a recurring worker.
---

# Run one Workbench job

The app persists requests; this skill owns the explicit execution boundary.

1. Read `docs/PRODUCT.md` and `docs/ARCHITECTURE.md`, then run
   `./workbench doctor`. Stop and report a failed readiness gate.
2. Recover expired leases and atomically claim at most one executable row:

   ```bash
   cd backend
   python3 scripts/codex_recover_agent_runs.py --pretty
   python3 scripts/codex_pick_agent_run.py --claim --pretty
   ```

3. Stop successfully if the queue is empty. Never poll, fabricate work, or
   claim a future-dated row early.
4. Follow the claimed `execution_contract`, frozen inputs, requested skill,
   and model policy. For `stock-initial-research`, use `company-research`:
   bounded collection, common research spine, sector archetype, company
   overlay, structured snapshot, and named evidence gaps.
5. Heartbeat during long work. Deterministic services own financial math. Run
   an independent strict verifier before exposing investment judgment.
6. Save or fail the same `agent_run_id`, preserving source IDs/times,
   assumptions, actual model metadata when available, verification status, and
   gaps. Stop after this one row.
