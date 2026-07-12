---
name: workbench-run-queue
description: Execute exactly one explicitly queued Stock Analysis Workbench job and stop. Use when the user invokes $workbench-run-queue or asks Codex to run the next queued Research, company-valuation, or portfolio-review job. Never create, enable, or imitate a recurring worker.
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
   and model policy. For `stock-initial-research` or `stock-company-review`, use `company-research`:
   bounded collection, common research spine, sector archetype, company
   overlay, and the exact contract frozen in the row. V2 jobs require the
   canonical archetype-pack lookup and one-to-one focus-marker accounting;
   frozen v1 jobs use the legacy v1 section of that skill and may not submit a
   v2 artifact. A company review must bind the immediately prior snapshot,
   compare history explicitly and save only the next version. For
   `stock-company-valuation`, use `company-valuation`: require
   its frozen ResearchSnapshot and input fingerprints, run only the frozen
   ready method pack and deterministic engine, obtain independent strict
   verification for the exact draft, then save it unchanged.
   For `stock-portfolio-review`, use `portfolio-review`: interpret only its
   frozen snapshot, mappings, deterministic analytics, provider-labelled
   history methods, risk-context fingerprint and eligible valuation IDs. Stop
   if retained rows do not reconcile to the provider total. Never sync myfund,
   repair a mapping, replace a valuation, or turn aligned sensitivity into
   probability/covariance.
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
   For portfolio review, persist the independent exact-draft verdict with
   `backend/scripts/codex_verify_portfolio_review.py`, then attach only its
   `verification_run_id` and save the unchanged draft with
   `backend/scripts/codex_save_portfolio_review.py`.
   Preserve requested role/model/reasoning separately from
   `actual_host_model`. Use `host deployment not exposed` when the host does
   not disclose it, and name any substitution or escalation without inferring
   a deployment from the requested slug. A disclosed host identity that
   differs from the requested model requires an explicit
   substitution/escalation note; exact identities need none.
7. Preserve source IDs/times, assumptions, actual model metadata when
   available, verification status, and gaps. Stop after this one row.
