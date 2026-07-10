# Implementation Tasks

Stable task IDs for implementation and review. `AGENTS.md` is authoritative for
working rules; `docs/plan-research-platform.md` is authoritative for the target
architecture. This file is the only current execution/status list.

Completed implementation history is summarized below. Detailed rationale lives
in the stage plans, validation notes, learning notes, and git history.

When a stage closes, keep only its summary and stable IDs here. Move detailed
task/plan history to `docs/archive/<topic>-<date>.md`, add a `CHANGELOG.md`
decision entry, and leave a pointer from the live document. Never use this file
as a session diary.

## Execution sequence

Take the first unchecked item. Each item should be a bounded, verifiable slice.

1. CX.15a — ESPI completeness watermark and pagination.
2. CX.15b — `workbench start` pre-session hook.
3. [x] IL.1 — decision journal.
4. [x] IL.2 + CX.15c — thesis-change diff and ESPI/queue actions.
5. [x] IL.3 — falsifiers and thesis-at-risk ordering.
6. [~] IL.4/IL.4a — read-only positions and myfund API-key/CSV import.
7. IL.5 — UI alignment and screenshot QA.
8. CX.16a–d — first mixed-outcome historical cohort replay.
9. RT2.3 — ledger-grade issuer/ESPI pilot, reusing CX.15a.
10. RT stages in order; add CX.16e/f and CX.17 only when prerequisites exist.

## Completed work

| IDs | Result | Source of detail |
|---|---|---|
| P0.1–P0.6 | Monorepo, local Postgres, FastAPI health endpoint, Next proxy, first migration, README. | `PLAN.md` §2, `docs/learning/phase-0.md` |
| P1.0–P1.8 | Polite BiznesRadar/price ingestion, fixtures, metrics inputs, refresh/read APIs and watchlist. | `PLAN.md` §§5–7, scraper-doctor skill |
| P2.1–P2.6 | PortalAnaliz login, topic linking, incremental forum sync and upvotes. | `PLAN.md` §5, `docs/learning/phase-2.md` |
| P3.1–P3.6 | Pure metrics, TTM/prescore/forecast, dossier and forum summary. | `PLAN.md` §7, `docs/learning/phase-3.md` |
| P4.1–P4.8 | Watchlist, stock pages, financials/charts/forecast/forum/settings UI. | `PLAN.md` §7, `docs/learning/phase-4.md` |
| P5.1–P5.7/P5.9 | Strategy skill, rubric, examples, explicit analysis path, history and forum distiller. | `skill/`, `docs/plan-stage-thesis.md` |
| TH.1–TH.5, TH.2b | Source-grounded generic thesis engine, Malik profile, guarded optional refinement and validation. | `docs/plan-stage-thesis.md`, `docs/validation-thesis.md` |
| SC.1–SC.5 | Deterministic scenarios, bounded AI valuation, corpus enrichment and validation. | `docs/plan-stage-scenarios.md`, `docs/validation-scenarios.md` |
| CX.1–CX.9 | Codex contracts, provider-neutral runs, local scripts/MCP, skills, ESPI events, queue UI and deterministic replay. | `docs/plan-stage-codex-pivot.md` |
| CX.12 | Durable queue claim/save/complete lifecycle and local worker contract. Periodic execution is optional under CX.15. | `.codex/tasks/stock-queue-worker.md` |

P1.9 remains an optional premium-session compatibility feature. P5.8 is
superseded by RT.6. The legacy Claude path is retained only until CX.10.

## Stage CX — Codex-centered analyst operating system

Detailed contracts: `docs/plan-stage-codex-pivot.md`.

- [ ] **CX.10 Legacy provider sunset/archive.** Remove or archive Anthropic/
  Claude configuration, clients, direct analysis behavior and compatibility
  tests after RT1.3 migrates the remaining legacy calls. Verify with an
  `rg` sweep; preserve explicit migration notes and historical archives.
- [~] **CX.11 Backtest data readiness.** Price migration `0015` now records
  `scraped_at`; refreshes populate it and strict backtests exclude prices
  learned after the observation date or with unknown availability. Financial
  publication/version coverage, point-in-time snapshots and sufficient
  historical depth remain open. Walk-forward review is owned by CX.16/RT6.6.
- [~] **CX.13 Agent valuation evaluation.** Structured replay remains limited
  to saved `analysis_runs`; prose-only predictions remain `unknown`/
  `needs-human`, and an empty cohort now also returns `needs-human` with an
  explicit no-evidence warning. Do not change prompts or strategy rules
  without separated validation and `verifier_strict` review. Detail:
  `docs/plan-agent-valuation-backtest.md`.
- [~] **CX.14 UI workbench composition.** Explore now exposes deterministic
  source-ranking rationale and, after an explicit source refetch, queues up to
  15 stale quick analyses for stored companies older than seven days. Remaining
  work is the primary watchlist surface, compact operations rail,
  queue truthfulness, provenance/status density and responsive/accessibility
  checks, coordinated with RT4.5–RT4.7 and `docs/plan-ui-refactor.md`.
- [ ] **CX.15 Session-driven operation.** Keep ingestion and queue execution
  pull-based and local; periodic polling is opt-in only.
  - [x] **CX.15a** Persist `last_polled_at`, paginate GPW ESPI until the
    watermark with a hard cap, and gate queue creation on complete ingestion.
    Migration `0010`, strict parsers, fixture coverage, resumable cursors and
    incomplete-poll queue suppression are verified by the focused backend suite.
  - [x] **CX.15b** Make `workbench start` run health checks, pre-session poll,
    queueing and one queue-processing attempt, idempotently and non-blocking.
    The detached session hook is idempotent, stops at the durable queue claim
    boundary, and is covered by operator tests plus the fresh local runtime gate.
  - [x] **CX.15c** Add UI actions for ESPI re-check and one queue-processing
    attempt with visible progress and failure state. The queue action stops at
    the durable claim boundary; it does not execute a model.
  - [x] **CX.15d** Document periodic/hosted polling as an opt-in variant.
    The documented command only polls and queues after complete ingestion;
    overlapping runs, queue claims, model calls and approvals remain outside
    the scheduled job.
- [~] **CX.16 Historical cohort replay.** Research-only precursor to RT6.6.
  - [x] **CX.16a** Freeze a mixed cohort: documented hit, documented miss,
    control candidate and excluded unverified placeholder are recorded in
    `docs/backtest-cohort-cx16a.md`. No delisting was found in the stored
    corpus; selection, identity and availability limits remain explicit.
  - [~] **CX.16b** Reconstruct historical inputs with an explicit
    `estimated_period_lag` policy and restatement caveat. The engine now
    persists both; case identity, original filing versions and price coverage
    remain to be reconstructed before this slice can close.
  - [~] **CX.16c** The backtest engine now labels persisted output as
    `deterministic_prescore_only` and explicitly records that AI-refined output
    is excluded. Deterministic thesis/scenario range replay remains pending
    point-in-time case inputs.
  - [ ] **CX.16d** Compare 1/2/3-year outcomes and write per-case cards; small-n
    summaries are diagnostic, never proof.
  - [ ] **CX.16e/f** Optional multi-`as_of` and masked-AI research after the
    first cohort; contamination-risk results remain soft evidence only.
- [ ] **CX.17 Evidence-derived guidance.** After RT2.3, compute cited
  promise-vs-delivery/backlog/governance features and measure them in replay;
  models extract, deterministic code owns the numbers.

## Stage IL — investor decision loop

Thin, decision-first work that interleaves with RT.2–RT.4. Detail and privacy
rules: `docs/plan-research-platform.md` §3.0 and §9, plus `AGENTS.md`.

- [x] **IL.1 Decision journal:** append-only decision, confidence, thesis,
  invalidation and next-check form; under one minute; no overwrite of history.
  Migration `0011` stores a hashed thesis snapshot; corrections are new rows.
- [x] **IL.2 Change monitor:** compare deterministic dossier/event snapshots
  after a session; no scraping or model call in the diff computation.
  Migration `0012` stores one immutable change card per changed baseline.
- [x] **IL.3 Falsifiers:** explicit `holding`/`warning`/`fired` state with a
  required human/evidence reason; watchlist orders fired then warning cases.
  No status is inferred from metrics or models. Migration `0013` and company
  editor are covered by focused API/migration/UI build checks.
- [x] **IL.4 Position ledger:** read-only ticker, entry, size and sizing-rule
  flag; never an analysis score or AI input. Migration `0014` and the company
  context panel are covered by API/migration/build checks.
  - [~] **IL.4a myfund import:** CSV import and the documented official API
    adapter pin one portfolio, require explicit ticker mapping, surface
    unmatched rows and avoid login passwords. The live local API check reached
    myfund but returned a remote error, sanitized to `502 needs-human`; no
    position was imported and the sync is not treated as verified.
- [x] **IL.5 UI alignment:** canonical Report/Charts/Sources/Codex mapping,
  progressive disclosure, one canonical company read, and screenshot QA.
  Browser verification passed at desktop and 390px mobile widths: no page
  overflow, all four tabs remained reachable, and Sources/Codex content loaded.

## RT roadmap — next required stages

The order below is binding. `~` means a usable slice exists but the stage is not
complete. Do not deploy before RT.0–RT.6 prove the local workflow.

### RT.0 — trustworthy baseline

- [x] RT0.1–RT0.5: green baseline, real fixtures, `doctor`, local pilot and
  README/PLAN/TASKS reconciliation.
- Remaining only where noted in `TASKS.md`: clean-install automated browser
  smoke and any explicitly deferred external/provider checks.

### RT.1 — explicit, reproducible AI runs

- [~] RT1.1–RT1.6: deterministic dossier reads, run provenance, orchestrator,
  strict contracts and quota/cost accounting have usable slices.
- Next: migrate legacy direct-client compatibility and forum distillation,
  durable child-attempt detail, price reservations and async cancellation.

### RT.2 — evidence ledger and primary disclosures

- [~] RT2.1–RT2.2: immutable document/version/fact contracts and serving
  lineage exist; legacy rows remain honestly unlinked until refreshed.
- [~] RT2.3: ESPI/EBI detail ingestion now bridges stored reports into the
  immutable evidence ledger with source versions and unverified claim locators.
  Pilot issuer IR coverage for 3–5 watchlist companies and broader claim
  extraction remain open; the CX.15a watermark is shared by the poller.
- [ ] RT2.4–RT2.5: source terms/quality notes and corporate-action-aware
  long-history market-data evaluation.

### RT.3 — fundamental depth and company templates

- [~] RT3.0: low-request discovery seed exists; candidate scores remain
  transparent and do not claim strategy fit.
- [ ] RT3.1: cash conversion, working capital, capex, returns, dilution and
  normalized one-offs beyond the existing continuing-earnings slice.
- [ ] RT3.2–RT3.4: versioned templates, 2–3 real pilot archetypes and only
  template-driven macro/sector adapters.

### RT.4 — research case and operating-driver scenarios

- [~] RT4.1–RT4.4: persistent case state, driver assumptions, sourced/human/
  model labels, template scenario v2 and valuation sensitivity migration.
  - [x] RT4.1a: Add the durable `ResearchCase` root for one company and
    purpose, with explicit state/current step/`as_of`, one forward migration,
    read/write API contract and fixture tests. Forecast/scenario persistence
    remains out of scope until this root is extended and verified in the next
    case slice.
  - [x] RT4.1b: Show the case state in the company header and provide an
    explicit create action.
  - [x] RT4.1c: Edit case state and current step explicitly, surface blocked
    reasons, and include the selected workflow step in the report brief;
    persistence of assumption sets and step history landed in RT4.2a–c.
  - [x] RT4.2a: Add durable case-linked assumption sets for negative/base/
    positive/event scenarios with per-input provenance and purpose-scoped
    read/create/update API.
  - [x] RT4.2b: Add the compact scenario assumption editor, including
    per-input provenance and a visible saved-set list.
  - [x] RT4.2c: Retain an appendable history of case-step changes with an
    explicit transition reason and editor identity; legacy cases remain
    history-empty until a new transition is recorded.
  - [x] RT4.3a: Connect approved case assumptions to the scenario context and
    keep sourced, human and model suggestions distinct in the dossier/UI;
    approved inputs remain context-only until priced equations are added.
  - [x] RT4.3b: Map the typed approved driver keys into copied pure scenario
    inputs and expose deterministic sensitivity changes; drafts, rejected
    sets, unsupported keys and model suggestions cannot alter saved valuation.
  - [x] RT4.3c: Add the first industrial/consumer P&L template for
    revenue/margin, forecast net profit and C/Z or EV/EBITDA bridge, retaining
    the RT4.3b overlay as an explicit sensitivity rather than a hidden forecast.
  - [x] RT4.3d: Cash-flow/capex mapping, conversion snapshot,
    source-backed receivable/inventory delta and a tested P&L-to-FCF bridge
    are present; historical CF is kept separate to avoid double-counting WC.
  - [x] RT4.3e: Add explicit approved capex/WC forecast assumptions and a
    separate FCF valuation lens; it does not replace the current multiple lens
    and remains unavailable until its inputs are complete.
  - [x] RT4.4a: Gate priced scenario outcomes behind an approved FCF lens,
    representative industrial/financial/event-driven coverage, strict verifier
    pass, source lineage, math reconciliation and no-look-ahead checks; keep
    qualitative outcomes when any gate condition is missing.
- [~] RT4.5–RT4.7: report-first UI and manual QA slices exist; scenario rows
  now expose a qualitative negative/stable/improving company outcome and case
  assumptions have provenance-aware persistence/editor surfaces and appendable
  step history, while priced driver equations, automated
  screenshots/accessibility and representative industrial/financial/event-
  driven QA remain.
  - [x] RT4.5a: Add company-outcome conditions to C/Z, C/WK and EV/EBITDA
    rows, including fallback/missing-data and AI-event boundaries.
  - [~] RT4.5b: Priced outcomes now use the approved FCF equation only after
    the RT4.4a gate; the UI exposes every required verifier check and the
    verifier must bind to the current bridge fingerprint and dedicated
    `scenario-simulation` workflow. Deterministic simulations now expose
    verified math and priced probability mass. Remaining acceptance is
    representative persisted verifier evidence for industrial, financial and
    event-driven cases plus source/no-look-ahead approval.

### RT.5 — OpenAI orchestration and Codex workflow

- [~] RT5.4–RT5.5: `workbench` operator and research skill exist for current
  commands; extend only as case contracts land.
- [~] RT5.6: typed MCP save/verify now has a strict `scenario-simulation`
  approval boundary: deterministic scenario snapshot, current bridge
  fingerprint, priced gate and verifier checks must agree before `pass`; the
  keyless JSON-script fallback now applies the same guard.
- [ ] RT5.1–RT5.3, RT5.1b, RT5.2: Responses API adapter, model policy,
  bounded extraction/verification and prompt-injection isolation remain after
  the stable CLI/MCP contract; no provider call is implied by this boundary.

### RT.6 — judge, calibration and honest replay

- [ ] RT6.1–RT6.7: mixed-outcome gold cases, versioned judge, isolated
  evaluator, holdout-gated improvement loop, trace evals and strict walk-forward
  replay. CX.16 is the research-only precursor.

### RT.7 — deployment and expansion

- [ ] P6.1–P6.9: auth, deployment, backups, monitoring and optional hosted jobs
  only after local evidence, scenario and evaluation gates pass. Hosting plan:
  `docs/hosting-codex-automation.md`.

## Extension backlog

Only add these after a real pilot need and the relevant RT gate:

- additional company templates and source adapters;
- corporate-action-aware long price history;
- broader factor backtesting or weight tuning;
- hosted poller/worker and external notifications;
- new reusable Codex skills after stable contracts and gold cases.
