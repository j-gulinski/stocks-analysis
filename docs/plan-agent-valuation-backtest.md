# Agent Valuation Backtest Plan

Purpose: evaluate whether saved agent analyses and valuation memos were useful
decision support after time passed. This is not automatic trading advice. It is
a learning loop for model/workflow quality.

## Core idea

Current deterministic backtests replay the Malik strategy signal from stored
financial and price data. Agent valuation backtests replay a different object:
what an agent wrote in `analysis_runs.output` at a known `created_at`, using
only the saved `input_snapshot`, then compare it to later prices and later
source events.

The app should answer:

- Did the agent identify the right drivers, risks and data gaps?
- Was the valuation direction useful after 30/90/180/365 days?
- Was confidence calibrated, or did high-confidence notes fail?
- Which workflow/model role was useful for which company setup?
- What should change in prompts, required inputs or verifier checks?

## Data model proposal

Add `agent_evaluation_runs`:

- `id`
- `agent_run_id`
- `analysis_run_id`
- `strategy` such as `valuation_direction_v1`
- `evaluation_as_of`
- `outcome_windows` JSON
- `policy` JSON, including price source and horizon rules
- `summary` JSON
- `verification_status`
- `created_at`

Add `agent_evaluation_observations`:

- `id`
- `evaluation_run_id`
- `analysis_run_id`
- `company_id`
- `prediction` JSON
- `known_inputs` JSON
- `outcome` JSON
- `score` JSON
- `created_at`

`prediction` should be extracted from the saved output, not recomputed from
future data. Preferred fields:

- `direction`: positive, neutral, negative, unknown
- `expected_horizon_days`
- `confidence`
- `target_or_potential_pct`, if present and sourced
- `drivers`
- `risks`
- `verify_next`
- `data_gaps`

## Evaluation policy

Initial policy `valuation_direction_v1`:

- Eligible rows: `analysis_runs` with `created_at <= evaluation_as_of`,
  `workflow in stock-quick-analysis, stock-deep-analysis`, and saved output.
- Outcome windows: 30, 90, 180, 365 days from `created_at`.
- Price outcome: nearest stored trading day at or after each target date.
- Direction score:
  - positive prediction succeeds when return is above configured hurdle;
  - negative succeeds when return is below negative hurdle;
  - neutral succeeds when absolute return stays inside a neutral band;
  - unknown is not scored, but counts as a coverage gap.
- Confidence calibration: compare confidence bucket with hit rate and outcome
  magnitude.
- Verifier status:
  - strict when input snapshots and price windows are complete;
  - `needs-human` when snapshots are missing or the prediction field is
    inferred from prose.

## Implementation phases

1. Schema and parser:
   - Add tables and API schemas.
   - Implement pure Python extraction from `analysis_runs.output`.
   - Unit-test edge cases: missing direction, prose-only potential, absent
     price window, needs-human verifier status.

2. Replay service:
   - Build `services/agent_evaluation.py`.
   - Attach future price outcomes without adding them to `known_inputs`.
   - Persist evaluation runs and observations.

3. Codex contract:
   - Add `backend/scripts/codex_evaluate_agent_runs.py`.
   - Add MCP tool `evaluate_agent_runs`.
   - Add `stock-agent-evaluation` or extend `stock-backtest-review` with this
     workflow.

4. UI:
   - Add an "Agent Evaluation" section inside Backtest Lab.
   - Show model/workflow hit rate, confidence calibration and false-positive
     notes.
   - Keep all results marked `needs-human` until `verifier_strict` audits
     point-in-time snapshots and parsing assumptions.

5. Learning loop:
   - Save accepted lessons to `docs/learning/agent-evaluation.md`.
   - Do not modify prompts or strategy weights until train/validation periods
     are separated and verifier review passes.

## First useful slice

Implement phase 1 and 2 for saved `analysis_runs` only. Do not add broad
scraping or auto-prompt mutation. A good first run can evaluate whatever saved
Codex analyses already exist, even if many observations are marked
`insufficient_future_price` or `needs-human`.

Status 2026-07-09: implemented for structured saved outputs:

- ORM tables: `agent_evaluation_runs`, `agent_evaluation_observations`.
- Service: `services/agent_evaluation.py`.
- API: `POST/GET /api/agent-evaluation-runs`.
- Script: `backend/scripts/codex_evaluate_agent_runs.py`.
- MCP tool: `evaluate_agent_runs`.
- Frontend: dashboard "Agent Evaluation" panel can create runs, list recent
  saved evaluations, expand observation details, and show verifier state,
  structured prediction source, model role, outcome windows and missing-data
  warnings.

Current parser intentionally avoids prose inference. It reads structured
`prediction.direction`, `potential.value_pct`, `valuation.potential.value_pct`,
`expected_upside_pct`, or `upside_pct`. Missing structured direction is
`unknown` and keeps the evaluation `needs-human`.

Status 2026-07-09 follow-up: quick/deep analysis workflows now require a
`stock-result-verifier` pass before `verification_status=pass`. New verified
outputs should therefore expose replay-ready `prediction`, deterministic
`potential`, and `result_quality` fields. Next evaluation runs should prefer
those newer outputs; older prose-only rows remain useful as negative/coverage
examples but must not be treated as scored prediction evidence.
