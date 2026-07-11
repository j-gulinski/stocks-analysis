---
name: workbench-run-queue
description: Execute exactly one explicitly queued Stock Analysis Workbench job and stop. Use when the user invokes $workbench-run-queue or asks Codex to run the next queued Research or company-valuation job. Never create, enable, or imitate a recurring worker.
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
   overlay, and the exact contract frozen in the row. V2 jobs require the
   canonical archetype-pack lookup and one-to-one focus-marker accounting;
   frozen v1 jobs use the legacy v1 section of that skill and may not submit a
   v2 artifact. For `stock-company-valuation`, use `company-valuation`: require
   its frozen ResearchSnapshot and input fingerprints, run only the frozen
   ready method pack and deterministic engine, obtain independent strict
   verification for the exact draft, then save it unchanged.
5. Heartbeat during long work. Deterministic services own financial math. Run
   an independent strict verifier before exposing investment judgment.
6. For company research, the separate verifier first records its verdict with
   `verify_research_snapshot` (or the matching JSON-in script) against the
   exact draft. Add the returned `verification_run_id` to the unchanged draft,
   then save through `save_research_snapshot` or
   `backend/scripts/codex_save_research_snapshot.py`.
   The strict gate creates the immutable artifact, terminal status and lease cleanup.
   Never store this result through the generic analysis adapter.
   For company valuation, use only the canonical valuation verification and
   save API/MCP adapters named in the claimed execution contract; never invent
   a script, use direct SQL, or fall back to generic completion.
7. Preserve source IDs/times, assumptions, actual model metadata when
   available, verification status, and gaps. Stop after this one row.
