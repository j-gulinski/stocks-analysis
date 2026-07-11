# Stock Queue Worker

Use this prompt for a manual Codex thread, a background Codex thread, or a
scheduled Codex run that should process work requested from the web UI.

The recommended unattended topology is two bounded processes: the Workbench
process collects evidence and queues work; a standalone Codex scheduled task
claims and completes one run. `workbench start` remains a valid session-triggered
collector, and the system stays correct when no scheduler is enabled.

Do not turn the FastAPI process into an implicit AI worker. A single app process
may collect, refresh and queue deterministic work, but Codex skills still need
an explicit supervised/scheduled Codex execution boundary. This keeps the app
usable without an OpenAI API key and makes failures visible in `agent_runs`.

## Objective

Process queued Stock Analysis Workbench `agent_runs` from
`/Users/jgulinski/Claude/Projects/stocks-analyzis` and save structured,
verifier-gated results back to the app. Do not rely on chat memory as the
source of truth.

## Steps

1. `cd /Users/jgulinski/Claude/Projects/stocks-analyzis`.
2. Read `docs/project-guardrails.md` and the relevant `.agents/skills/stock-*`
   skill for the claimed workflow.
3. Recover expired leases before claiming. This is safe to run every cycle:

   ```bash
   cd backend
   python3 scripts/codex_recover_agent_runs.py --pretty
   ```

4. Claim one queued run atomically. Keep any model requested by the UI; only
   supply a default when the queue row has no model metadata:

   ```bash
   cd backend
   python3 scripts/codex_pick_agent_run.py --claim --pretty
   ```

5. Follow the returned `execution_contract`; its `requested_model` and
   `orchestrator_model` are user-visible routing metadata. The concrete host
   deployment may remain unavailable to the app and must not be guessed.
6. Use the repo MCP tools or JSON scripts to gather only stored/sourced data.
7. Follow the claimed skill's routing. For `stock-deep-analysis`, complete the
   catalyst, backlog/order-book and management/governance evidence loop, then
   use an independent strict verifier to decide the final prediction/confidence
   and approve or reject the result.
   Any UI-visible verified result must pass both `stock-result-verifier` and
   `stock-verifier`.
   The source-completion pass must attempt catalyst, backlog/order book and
   management/governance research. PortalAnaliz/BiznesRadar are discovery
   leads; preserve primary issuer/ESPI/EBI/GPW evidence or record `not_found`.
   Do not return those three topics as generic instructions to the user.
   When the scheduled task itself runs on the strict-verifier model, launch the
   bounded draft pass explicitly with local Codex CLI using the requested
   analyst model, for example `codex exec -m <requested-model> -s read-only
   --ephemeral -C <repo>`. If local CLI execution is unavailable, perform the
   bounded draft directly through the matching skill and keep the verifier
   independent. Give the draft pass the claimed run id and frozen dossier/source
   manifest, then let the parent strict-verifier task independently correct or
   approve it. Never substitute a same-model self-review.
8. During a long run, heartbeat at least every 10 minutes and before/after a
   source-completion or verifier pass. Use the same worker id that claimed the
   row:

   ```bash
   cd backend
   python3 scripts/codex_heartbeat_agent_run.py \
     --agent-run-id 123 --worker-id "codex:my-worker" --pretty
   ```

9. Save results with the same `agent_run_id`, for example:

   ```bash
   cd backend
   python3 scripts/codex_save_analysis.py SNT \
     --workflow stock-quick-analysis \
     --model-role worker_standard \
     --model gpt-5.3-codex-spark \
     --verification-status needs-human \
     --agent-run-id 123 \
     --input result.json \
     --pretty
   ```

   For watchlist-level or candidate-scout results that are not tied to one
   company analysis, complete the row directly:

   ```bash
   cd backend
   python3 scripts/codex_complete_agent_run.py \
     --agent-run-id 123 \
     --model-role worker_standard \
     --model gpt-5.3-codex-spark \
     --verification-status needs-human \
     --input result.json \
     --pretty
   ```

10. If no queued rows exist, report that the queue is empty and stop. Do not
    poll sources or create speculative work from inside the worker.

If the local MCP server is unavailable, use the equivalent fallback script:
`python3 scripts/codex_mark_verification.py --analysis-run-id 123
--verifier-model codex-host --verdict needs-human --input verifier.json`.
It applies the same strict scenario-simulation guard and never needs an API
key.

## Success Criteria

- The claimed `agent_run` no longer remains stuck in `queued`.
- A running row has a live `lease_owner`, `heartbeat_at` and expiry; a crashed
  worker can be requeued safely, with a three-attempt cap before `needs-human`.
- Saved output includes `workflow`, `model_role`, `model`,
  `verification_status`, `input_snapshot`, `output`, and `verification`.
- The result contains company-level negative/base/positive outcomes, not only a
  bare multiple or price change.
- Material investment claims are sourced or marked as gaps.
- No deterministic numbers are invented by the model.
- A size/sweet-spot mismatch is strategy-fit context, not a company risk.
