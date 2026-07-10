# Documentation archive

The live documentation is intentionally small:

- `AGENTS.md` — project instructions and documentation lifecycle;
- `TASKS.md` — current execution queue and open acceptance criteria;
- `docs/plan-research-platform.md` — canonical target architecture and RT order;
- `PLAN.md` — stable architecture overview;
- active stage plans — detailed contracts only while work is active.

When a phase or stage closes:

1. verify its acceptance criteria and record the evidence in the validation
   note and `CHANGELOG.md`;
2. reduce `TASKS.md` to a one-line or table summary with stable IDs;
3. move superseded detailed task/plan prose here as
   `<topic>-<YYYY-MM-DD>.md`, or retain it in git when the compact live page
   already preserves the durable contract and validation pointer;
4. leave a link from the live document and label the archive historical;
5. search for stale references before marking the cleanup complete.

Do not archive guardrails, active skills, source-grounded strategy rules,
validation evidence, or the canonical research-platform plan while they remain
operationally binding.

Current detailed archives:

- [`changelog-archive-2026-07-07.md`](../changelog-archive-2026-07-07.md)
- [`changelog-archive-thesis-2026-07-08.md`](../changelog-archive-thesis-2026-07-08.md)

Several completed stage plans now use compact index pages. Their removed
implementation detail remains recoverable in git history; validation evidence
and current acceptance criteria remain linked from the live pages.
