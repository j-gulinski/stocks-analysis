# Stock Queue Worker

Use this prompt for a manual Codex thread, a background Codex thread, or a
scheduled Codex run that should process work requested from the web UI.

## Objective

Process queued Stock Analysis Workbench `agent_runs` from
`/Users/jgulinski/Claude/Projects/stocks-analyzis` and save structured,
verifier-gated results back to the app. Do not rely on chat memory as the
source of truth.

## Steps

1. `cd /Users/jgulinski/Claude/Projects/stocks-analyzis`.
2. Read `docs/project-guardrails.md` and the relevant `.agents/skills/stock-*`
   skill for the claimed workflow.
3. Claim one queued run:

   ```bash
   cd backend
   python3 scripts/codex_pick_agent_run.py --claim --model gpt-5.3-codex-spark --pretty
   ```

4. Follow the returned `execution_contract`.
5. Use the repo MCP tools or JSON scripts to gather only stored/sourced data.
6. Follow the claimed skill's routing. For `stock-deep-analysis`, use
   `gpt-5.3-codex-spark` for the source-completion loop and full draft, then use
   the strongest model available on the current Codex host (`verifier_strict`, high)
   to decide the final prediction/confidence and approve or reject the result.
   Any UI-visible verified result must pass both `stock-result-verifier` and
   `stock-verifier`.
   The source-completion pass must attempt catalyst, backlog/order book and
   management/governance research. PortalAnaliz/BiznesRadar are discovery
   leads; preserve primary issuer/ESPI/EBI/GPW evidence or record `not_found`.
   Do not return those three topics as generic instructions to the user.
   When the scheduled task itself runs on the strict-verifier model, launch the
   bounded draft pass explicitly with local Codex CLI, for example
   `codex exec -m gpt-5.3-codex-spark -s read-only --ephemeral -C <repo>`.
   Give it the claimed run id and frozen dossier/source manifest, capture its
   structured draft, then let the parent strict-verifier task independently
   correct/approve it. Never substitute a same-model self-review.
7. Save results with the same `agent_run_id`, for example:

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

8. If no queued rows exist, report that the queue is empty and stop.

## Success Criteria

- The claimed `agent_run` no longer remains stuck in `queued`.
- Saved output includes `workflow`, `model_role`, `model`,
  `verification_status`, `input_snapshot`, `output`, and `verification`.
- Material investment claims are sourced or marked as gaps.
- No deterministic numbers are invented by the model.
- A size/sweet-spot mismatch is strategy-fit context, not a company risk.
