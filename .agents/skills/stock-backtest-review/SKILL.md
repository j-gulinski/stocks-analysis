---
name: stock-backtest-review
description: Run and audit point-in-time strategy backtests for the Stock Analysis Workbench. Use when the user asks to backtest a strategy, replay a historical company case, compare signal to outcome, or review learning-loop evidence.
---

# Stock backtest review

Run point-in-time checks without look-ahead bias. Python computes the replay;
Codex interprets and verifies boundaries.

## Model routing

- Use `worker_standard` for formatting observations and flagging anomalies.
- Use `analyst_deep` for interpreting patterns across several backtests.
- Use `verifier_strict` for look-ahead audit before any learning note or
  strategy adjustment is accepted.

## Procedure

1. Capture request:
   - strategy name, default `malik_v1`
   - ticker or universe
   - `from_date` and `to_date`
   - outcome windows, if specified
2. Run the local contract:
   - Prefer MCP `run_backtest`.
   - If MCP is unavailable, run `cd backend && python3 scripts/codex_run_backtest.py --strategy malik_v1 --from-date YYYY-MM-DD --to-date YYYY-MM-DD`.
   - Add ticker/universe arguments when the tool or script supports them.
   - Default financial availability is strict `scraped_at`: only rows scraped
     by `as_of_date` enter `known_inputs`.
   - For research-only historical experiments where exact report publication
     dates are missing, an explicit `estimated_period_lag` policy may be used.
     Treat those runs as `needs-human` until verifier review; do not use them
     as verified strategy evidence.
3. Enforce point-in-time rules:
   - `known_inputs` may include only data published and scraped by `as_of_date`.
   - `estimated_period_lag` runs must clearly state the assumed lag and the
     fact that it is a proxy, not a real publication timestamp.
   - Future returns attach only after signal creation.
   - Strategy-weight changes require documented before/after validation sets.
   - If a run has zero observations, report that as insufficient stored price/data
     coverage instead of inventing a result.
4. Verify:
   - Run `stock-verifier` in backtest mode.
   - Fail any result with look-ahead leakage, missing date boundaries, or model
     interpretation presented as deterministic return math.

## Output contract

Return or save:

- `workflow`: `stock-backtest-review`
- `strategy`
- `period`
- `known_inputs_policy`
- `signals`
- `outcomes`
- `false_positives`
- `false_negatives`
- `learning_notes`
- `verification_status`
