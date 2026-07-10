# UI refactor — compact contract

**Status:** partial baseline. Remaining work is IL.5 / RT4.5–RT4.7 in
[`TASKS.md`](../TASKS.md); this page records only the acceptance bar.

## Target experience

The app is a dense analyst workspace, not a marketing dashboard. A company
case opens with one compact decision brief: company, `as_of`, freshness,
workflow state, blockers and next action. Progressive sections then expose:

1. evidence and source lineage;
2. business model and operating drivers;
3. performance and deterministic calculations;
4. thesis, falsifiers and next checks;
5. editable scenarios and valuation bridge;
6. Codex review runs, provenance and validation status;
7. append-only journal and monitoring changes.

## Non-negotiables

- Clearly distinguish sourced fact, deterministic result, human assumption,
  model suggestion and approved conclusion.
- Do not repeat the same verdict in multiple cards.
- Show draft/verified/rejected/needs-human status for model output.
- Preserve Polish financial labels/formatting, accessible contrast/focus,
  responsive layouts and useful empty/error/conflict states.
- Refresh and AI progress belong in an activity drawer or equivalent; page
  reads must not trigger hidden model calls.

## Verification

Use representative industrial, financial and event-driven cases. Run focused
tests, frontend build, accessibility checks and desktop/mobile screenshots;
record failures honestly. Do not finalize the redesign until RT.1–RT.3 case,
evidence and scenario contracts are stable.
