# Stage SC — scenario simulation (historical)

**Status:** complete. This compact page records the contract and evidence;
current execution belongs in [`TASKS.md`](../../../TASKS.md), and future design in
[`plan-research-platform.md`](../../plan-research-platform.md).

## Delivered

- Pure negative/base/positive scenario engine with multiple reversion,
  weighted expected value and bounded ranges.
- Strategy-aware valuation selection with honest fallbacks when a driver or
  metric is absent.
- Optional AI valuation refiner, WorkedCase corpus examples and frontend
  scenario rendering.
- Fixture-first tests and validation covering industrial, finance and
  energy-style valuation paths, including no-key behavior.

## Durable decisions

- The current engine is a valuation sensitivity tool, not a company operating
  simulation. It must migrate into RT.4 driver-based scenarios.
- Each deterministic row may now expose a qualitative company outcome
  condition, but its target price remains a multiple-only illustration until
  RT.4 adds priced operating-driver equations.
- Deterministic code owns multiples, weights, ranges and scoreable outputs;
  AI may explain or challenge them only through a guarded contract.
- Missing EBITDA, multiple drivers or history stays visible and may trigger a
  labelled fallback; it is never fabricated.
- AI-refined prose is not a backtest result. Replay uses frozen deterministic
  inputs and explicit point-in-time rules.

## Evidence and follow-up

- Validation: [`validation-scenarios.md`](../../validation-scenarios.md).
- Target migration: [`plan-research-platform.md`](../../plan-research-platform.md)
  §6 and RT.4.
- Detailed stage history remains in git and the dated changelog archives.
- No SC task is currently open; extend only through the RT roadmap.
