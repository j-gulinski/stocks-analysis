# Project guardrails

Read this file at the start and end of every phase or substantial work package.
It is the quality bar for the Stock Analysis Workbench.

## Product purpose

- Build a personal GPW analysis workbench for evidence-based investing, not a
  generic dashboard and not a trading-signal toy.
- The app must make it easier to gather facts, compare scenarios, verify theses,
  learn from past/future examples, and decide what to inspect next.
- Codex is the analyst/operator. Postgres plus source snapshots are the system
  of record. Chat memory is never the source of truth.

## Non-negotiable quality rules

- Every claim that can influence an investment view needs a source, input field,
  or explicit "unknown/gap" label.
- No fabricated numbers. If a value is absent, say it is absent and route it to
  `verify_next`, `data_gaps`, or `needs_human`.
- No direct buy/sell advice. Produce decision support: thesis, catalysts, risks,
  invalidation points, scenario ranges, and next checks.
- Deterministic math belongs in Python services and tests. Model reasoning may
  interpret, summarize, challenge, and verify, but it must not invent computed
  outputs.
- Scrapers remain polite and isolated: all HTTP through `scrapers/http.py`;
  parser changes require fixture tests.
- Keep implementation simple until the next extension point is truly needed.
  Do not build broad crawlers, autonomous trading, or generalized agent
  machinery before the local workflow proves value.

## Codex/model discipline

- `AGENTS.md` §Operating policy is the binding source for model selection and
  execution workflow. Use its exact ladder: GPT-5.3 high for testing/mechanical
  work only; Luna medium for basic implementation; Terra high for default
  implementation; Sol high for high-complexity work; and Sol ultra only for
  exceptional hardest work.
- Use the stronger suitable model at its full appropriate reasoning level. Do
  not lower model quality or reasoning merely to optimize an assumed budget
  limit; record the selected model/reasoning pair, actual host model and any
  substitution or escalation.
- Select the tier before work begins, escalate one tier only on evidence, and
  record any escalation or same-reasoning-level host substitution for persisted
  runs.
- UI-visible investment output must pass `verifier_strict`.
- Track in the session what work is delegated, which model role is used, and how
  the result was verified.

## UI standard

- The UI is an analyst workspace, not a marketing page.
- First screen should show useful work: watched companies, freshness, thesis
  state, scenarios, events, tasks, or queues.
- Use dense but readable layouts, stable dimensions, restrained styling, and
  clear source/provenance badges.
- Prefer Polish domain labels and English navigation where that convention
  already exists.
- Any Codex output visible in the UI must show status: draft, verified,
  rejected, or needs-human.

## Phase exit checklist

Before marking a phase or work package done:

- Re-read this file and the relevant plan section.
- Follow the required execution workflow in `AGENTS.md` §Operating policy.
- Update `CHANGELOG.md` with what changed, why, and key decisions.
- Update `TASKS.md` status.
- Add or update tests proportional to risk.
- Run focused verification commands and record failures honestly.
- Run `./workbench doctor`, `./workbench start`, and `./workbench status`,
  verify backend HTTP health and frontend readiness, and inspect matching logs;
  do not mark the phase done if this runtime gate fails.
- Confirm no secrets, local tokens, or private credentials were added.
- Confirm the result advances the investing workflow instead of adding
  impressive but unused machinery.
