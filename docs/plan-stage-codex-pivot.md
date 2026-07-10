# Stage CX — Codex-centered operating system

**Status:** foundation delivered; CX.10–CX.17 remain bounded follow-up work.
This compact contract complements the canonical RT roadmap and does not track
session progress. Use [`TASKS.md`](../TASKS.md) for status and
[`plan-research-platform.md`](plan-research-platform.md) for target
architecture.

## Operating model

Codex is a supervised analyst/operator over durable application state. The
application owns facts, calculations, evidence, queue state and saved runs.
Codex may gather, interpret, challenge and verify; it may not invent facts,
replace deterministic math or approve its own investment output.

The default loop is pull-based and session-driven:

```text
start/check -> poll evidence -> queue work -> claim one item
-> research with the matching skill -> strict verify -> save or reject
```

The worker stops at the durable claim boundary. A verifier-gated Codex run owns
the research and final save. Periodic or hosted execution is optional.

## Roles and routing

- `worker_standard`: mechanical extraction, fixtures and bounded data work.
- `analyst_deep`: cross-source synthesis and investment reasoning.
- `verifier_strict`: independent check of source grounding, schema, numbers,
  model-role discipline and look-ahead bias.

Use the lightest suitable host tier from `AGENTS.md`; role labels never replace
the concrete model record. A worker draft is never approval. If separate agents
are unavailable, run sequential worker-style and judge passes and record that
limitation in `docs/model-usage.md`.

## Contract for every run

Persist: company/purpose, input snapshot, source IDs and publication times,
`as_of`, prompt/skill/model versions, token/cost accounting, structured output,
validation result, verifier status, user feedback and timestamps. A run is
`queued → claimed → running → saved|rejected|needs_human|failed|cancelled`.

Every material conclusion must link to evidence or an explicit gap. Deterministic
services own scores, valuation, probabilities and ranges. Model output is
labelled as suggestion or approved conclusion only after verification.

## Workflows

1. **Pre-session brief:** refresh watched-company evidence, report freshness and
   blockers, create bounded queue items, never hide incomplete ingestion.
2. **Compact analysis:** read the dossier snapshot, return thesis/catalysts/
   risks/falsifiers/next checks with citations and unknowns.
3. **Deep analysis:** add company-specific business drivers, scenarios,
   valuation bridge and counter-thesis; do not duplicate deterministic cards.
4. **Candidate scout:** use transparent stored signals to shortlist; never
   claim strategy fit without the required evidence.
5. **Historical replay:** freeze point-in-time inputs, separate deterministic
   results from prose, include mixed outcomes and report survivorship limits.
6. **UI-requested run:** show progress and failure state, persist the same run
   contract, and expose draft/verified/rejected/needs-human status.

## Current implementation boundaries

- CX.15a: ESPI watermark, pagination, strict fixtures and completeness gate.
- CX.15b: idempotent `workbench start` health/pre-session hook with at most one
  queue claim; hook failure must not hide app readiness.
- CX.15c: UI re-check/one-attempt controls are delivered.
- CX.15d: the opt-in periodic/hosted polling boundary is documented; no
  scheduler or hosted model execution is enabled by default.
- CX.10: archive legacy provider calls only after RT1 migration.
- CX.11/CX.16: make point-in-time cohort replay honest before scoring.
- CX.13: continue valuation replay; prose-only predictions remain unknown.
- CX.14: finish workbench composition with RT.4 UI contracts.
- CX.17: derive guidance features only after primary evidence exists.

## Guardrails

No hidden model calls on reads, direct buy/sell advice, fabricated values,
unbounded crawling, autonomous trading, or hosted use of personal Codex
credentials. Parser changes require fixtures; all HTTP uses the polite scraper
boundary. See [`project-guardrails.md`](project-guardrails.md), the repository
skills and the strict verifier skill.
