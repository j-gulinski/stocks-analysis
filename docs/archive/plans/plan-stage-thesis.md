# Stage TH — investment thesis (historical)

**Status:** complete. This page is a compact index, not an active execution
plan. Current work is tracked only in [`TASKS.md`](../../../TASKS.md); target
architecture is in [`plan-research-platform.md`](../../plan-research-platform.md).

## Delivered

- Source-grounded Malik/OBS strategy profile and evidence-linked gaps.
- Deterministic thesis engine with explicit one-off, catalyst, risk and
  invalidation fields.
- Optional deterministic-first AI refinement with structured output, no-key
  fallback and fabrication guards.
- Frontend thesis panel and historical/current validation for DGN, SNT and
  current-cap sanity.

## Durable decisions

- Facts and arithmetic stay in Python; models interpret, challenge and label
  unknowns.
- Entry quality is analysis context, never a buy signal.
- Missing evidence remains `unknown`/`verify_next`; it is never inferred as a
  failure or filled with a plausible number.
- The current thesis output will be absorbed into the persistent research case
  and verifier workflow in RT.1–RT.4.

## Evidence and follow-up

- Validation: [`validation-thesis.md`](../../validation-thesis.md).
- Strategy source/spec: [`strategy-malik.md`](../../strategy-malik.md) and
  [`skill/SKILL.md`](../../../skill/SKILL.md).
- Detailed implementation history: git history and
  [`changelog-archive-thesis-2026-07-08.md`](../changelog-archive-thesis-2026-07-08.md).
- No TH task is currently open; do not reopen this stage for routine RT work.
