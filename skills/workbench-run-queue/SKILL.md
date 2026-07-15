---
name: workbench-run-queue
description: Drain the explicitly queued Stock Analysis Workbench jobs with lease recovery, independent verification, and bounded failure caps. Use when the user invokes $workbench-run-queue or asks Codex to clear queued Research, valuation, or portfolio-review work. Never create a recurring worker.
---

# Drain the Workbench queue

The app persists requests; this skill owns one explicit queue-draining session.

1. Read `docs/PRODUCT.md` and `docs/ARCHITECTURE.md`, then run
   `./workbench doctor`. Stop and report a failed readiness gate.
2. Recover expired leases once:

   ```bash
   cd backend
   python3 scripts/codex_recover_agent_runs.py --pretty
   ```

3. Loop until the queue is empty or a stop condition fires:
   - atomically claim the next eligible row with
     `python3 scripts/codex_pick_agent_run.py --claim --pretty`;
   - honor the job's exact requested public model and reasoning effort from the
     canonical Architecture policy; if this surface cannot select it, record
     the actual host as unavailable plus the substitution instead of silently
     treating every job as the current model;
   - follow its frozen execution contract and heartbeat its lease;
   - load and follow the workflow skill named by that contract; for valuation,
     the Codex context itself must perform the company-specific causal analysis
     in `company-valuation` before invoking deterministic computation—scripts
     may validate or price the draft, but may not synthesize it by filling a
     reusable grid;
   - run deterministic collection/calculation before judgment;
   - obtain genuinely independent strict verification for the exact draft;
   - save through the workflow's canonical adapter so the row terminalizes
     and its lease clears;
   - claim the next row.
4. Supported workflows:
   - `stock-initial-research` and `stock-company-review` use
     `company-research` v3, including the five source-channel attempts,
     company-specific profile, forward Outlook, exact verification, and
     immutable snapshot save;
   - `stock-company-valuation` uses `company-valuation` v4. The frozen row
     supplies the Research/base boundary; Codex reads the complete dossier and
     reasons through company-specific mechanisms, runway, falsifiers, annual
     driver impacts, capital allocation/net debt, terminal economics, method
     fit and probabilities. Python owns only lineage, timing, reconciliation
     and valuation math;
   - `stock-portfolio-review` interprets only its frozen snapshot, mappings,
     analytics, risk context, eligible valuations, and gaps.
5. Stop the session when any of these bounded safety caps fires:
   - the same job fails twice;
   - three consecutive jobs fail;
   - a job reaches `needs-human` because identity, integrity, access, or math
     cannot be resolved safely.
6. An empty queue is a successful terminal state. Report processed, failed,
   recovered, and remaining counts plus the blocking row when a cap fired.

Preserve source IDs/times, assumptions, requested and actual model metadata,
substitutions, verification records, and named gaps. Never fabricate work,
claim future-dated rows early, schedule a recurring worker, mutate a portfolio,
or issue a transaction instruction.

Routing summary: Research uses `gpt-5.6-terra` high, valuation uses
`gpt-5.6-sol` high, ordinary portfolio interpretation uses `gpt-5.6-terra`
medium, clear repeatable support may use `gpt-5.6-luna` low, and every strict
decision verifier uses an independent `gpt-5.6-sol` high. Mechanical coding
checks may use `gpt-5.3-codex-spark` outside the artifact queue when available.
xhigh and Max require evidence; Ultra is divisible multi-agent orchestration,
not a model.
