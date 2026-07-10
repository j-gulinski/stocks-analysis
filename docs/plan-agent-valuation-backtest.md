# Agent valuation replay — compact contract

**Status:** research-only precursor to RT.6; execution is tracked as CX.13 and
CX.16 in [`TASKS.md`](../TASKS.md). This is not a performance claim or a live
investment signal.

## Purpose

Test whether saved valuation ranges and their explanations are useful when
replayed against information that was actually available at the historical
`as_of` date. Keep this separate from parser tests, AI extraction tests and a
market-wide strategy backtest.

## Required record

Each case needs: ticker/company, historical `as_of`, source publication dates,
frozen dossier and scenario inputs, strategy/template version, model/skill/run
metadata, deterministic valuation output, optional AI output, prediction
confidence, outcome horizon and benchmark. Unknown fields remain unknown.

## Evaluation rules

- Start with a mixed cohort: winners, controls, failures and delistings where
  possible; record survivorship and estimated-lag limits first.
- Freeze inputs before running the model; no later restatements, forum posts or
  current prices may leak into the case.
- Score deterministic ranges and direction separately from prose quality.
- Report 3/6/12/24-month outcomes, benchmark-relative return, adverse excursion,
  falsification timing and confidence calibration. Small samples are diagnostic,
  never proof.
- Hold out cases for evaluation. Do not tune prompts, weights or templates on
  the same cases used for the reported result.

## Gate

Do not publish strategy performance until immutable point-in-time evidence,
corporate-action-aware total-return prices, a declared universe, delistings,
frozen versions and an untouched holdout exist. See RT.6 in the canonical plan.
