# Changelog / decision log

Short durable ledger of meaningful project decisions and completed slices.
Detailed implementation history belongs in the referenced plans, validation
notes, archives, and git history. `TASKS.md` is the source of truth for current
completion status; entries below are historical snapshots.

Every code, schema, plan, or configuration change must add a concise entry.

---

## 2026-07-10 · Hard documentation compaction

Reviewed the Markdown documentation tree and reduced superseded stage plans,
the legacy design reference, UI contract, expert review, hosting note and
valuation replay plan to compact durable contracts and pointers. Preserved
operational instructions, source-grounded strategy rules, validation evidence,
the canonical research-platform plan and active skills. Updated the archive
lifecycle note to make compact pages and git-recoverable historical detail
explicit.

## 2026-07-10 · Clarified uncertain model classification

Removed the ambiguous instruction to default to the Medium tier when unsure.
`AGENTS.md` now says to choose the lightest plausible tier, while preserving
the explicit routing: GPT-5.3 high for capable testing/mechanical work, Terra
high for ordinary implementation, Sol high for high-complexity work, and Sol
ultra only after Sol high proves insufficient.

## 2026-07-10 · Corrected model routing ladder

Corrected the active routing policy to the requested escalation ladder:
GPT-5.3 high only when capable for testing/mechanical work, Luna medium as the
fallback when GPT-5.3 is insufficient there, Terra high for default
implementation, Sol high for high-complexity work, and Sol ultra only for
exceptional hardest work. Updated AGENTS, guardrails, the active
research-platform plan and the model usage ledger.

## 2026-07-10 · Delegated worker and independent judge policy

Added an AGENTS workflow for splitting meaningful medium/high-complexity work
into bounded worker loops, integrating through a manager, and judging the
integrated result in an independent review pass. Trivial or tightly coupled
work remains single-agent; overlapping writes are prohibited. When separate
agent tooling is unavailable, the workflow requires sequential worker-style
and judge passes with the limitation recorded in `docs/model-usage.md`.

Corrected the usage ledger so the documentation-only policy edit is classified
as testing/mechanical GPT-5.3-tier work; the earlier CX.15 implementation
remains correctly classified as Medium-tier work.

## 2026-07-10 · CX.15a closeout and CX.15b startup hook

Closed the ESPI completeness slice after verifying migration `0010`, strict
list/detail fixtures, watermark continuation after the hard page cap, detail
retry behavior, and the rule that incomplete ingestion never queues a Codex
brief. Added a detached `workbench start` session hook that runs the
pre-session poll/queue path and claims at most one durable queue item; startup
health remains independent of polite source latency or hook failure. Repeated
starts skip the hook while the application is already ready or while the same
hook PID is still active. The hook stops at the queue boundary—Codex remains
responsible for the verifier-gated workflow and final save.

Implementation-phase schema decision: keep this slice in the single `0010`
migration. Do not preserve or repair already-generated local database state with
a compatibility migration; recreate disposable local data from the current
chain when needed.

Added `docs/model-usage.md` and an AGENTS rule requiring per-session model,
role, tier, substitution/escalation and verification records so routing quality
and task division can be measured over time.

## 2026-07-10 · Documentation consolidation and archive lifecycle

Made `AGENTS.md` the single authoritative instruction file and reduced
`CLAUDE.md` to a compatibility pointer. Compacted `TASKS.md` to the live queue,
open acceptance criteria and concise completed-stage summaries; `PLAN.md` now
points status/order readers to `TASKS.md` and the research-platform plan.
Marked TH/SC plans as historical references and added `docs/archive/README.md`
with the rule for moving closed task/plan detail into dated archives while
preserving stable IDs and acceptance evidence. Guardrails, skills, strategy
specification, validation notes and the canonical research-platform plan remain
active rather than being archived.

## 2026-07-10 · Operating policy and execution order

- Added the binding effort-based model-routing policy to `AGENTS.md` and
  aligned `CLAUDE.md`, guardrails, plans, and RT5 tasks with it.
- `TASKS.md` now has one ordered execution queue. Active work is session-driven
  ESPI/queue processing, then the investor decision loop, validation cohort, and
  the RT roadmap.
- Historical model names remain run metadata; they do not override the selected
  model tier. UI-visible investment output remains verifier-gated.

## 2026-07-10 · CX.15 — session-driven operation

The default operating model is local and pull-based: ingest and process during
the user's session, not through an always-on poller. Away-period correctness
comes from retrospective completeness. Periodic or hosted polling is optional.

CX.15a is in progress in the working tree: it adds `list_poll_states`, a GPW
ESPI pagination watermark, strict page/detail parsing, completeness gating, and
fixtures. The startup hook and UI re-check actions remain open; see `TASKS.md`.

## 2026-07-10 · Stage IL — investor decision loop

Defined the small decision-first slice to interleave with RT work: append-only
decision journal, thesis-change diff, falsifier status and queue ordering,
read-only position ledger, optional myfund API-key/CSV import, and UI alignment.
The myfund integration is configuration/planning only; no broker credentials or
portfolio data are imported by this change.

## 2026-07-10 · Evidence-first report and verifier boundary

The company workspace is organized around a prepared report, scenarios,
evidence/financial audit, and Codex review. Saved model output must pass the
strict verifier and match the valuation snapshot before it is treated as
approved. Continuing-earnings normalization is used only when the complete
discontinued-operation bridge is present; otherwise the gap remains visible.

## 2026-07-10 · Local queue execution and hosted-boundary decision

Durable queue creation, claiming, saving, and verifier lifecycle are implemented
for supervised local Codex work. A local automation may execute the queue, but
it is not a deployable backend worker. The future hosted shape is Vercel UI plus
Railway API/Postgres and short-lived ingestion/notification jobs; personal
Codex credentials are not embedded in the hosted app. No deployment or external
notification was created.

## 2026-07-09 · CX / RT foundation

Added the Codex-centered workflow foundation: provider-neutral run storage,
explicit JSON script/MCP contracts, durable ESPI event ingestion, queue
lifecycle states, deterministic backtest replay, evidence/run provenance, and
the local `workbench` operator plus research skill. The system remains
evidence-first and does not present unverified or incomplete output as a
recommendation.

## 2026-07-08 · Stage TH — investment thesis

Completed the strategy-as-data thesis layer: generic deterministic engine,
Malik profile, evidence-linked gaps, fabrication guards, optional deterministic-
first AI refinement, and validation notes. Entry quality is analysis context,
not a buy signal. Detailed history: [thesis archive](docs/changelog-archive-thesis-2026-07-08.md).

## 2026-07-08 · Stage SC — scenario simulation

Completed deterministic negative/base/positive scenario simulation with
multiple-reversion valuation, weighted expected value, bounded AI valuation
support, corpus examples, tests, and validation notes. Detailed history is
retained in git and the stage plan/validation documents.

## 2026-07-07 · First vertical slice

Established the FastAPI + Next.js workbench, PostgreSQL/SQLite test split,
polite scraper boundary, BiznesRadar and PortalAnaliz ingestion, metrics,
forecast, dossier, watchlist, stock pages, forum support, and the initial
strategy/AI contracts. Durable scraper findings are maintained in
`skills/scraper-doctor/SKILL.md`. Detailed build-day history:
`docs/changelog-archive-2026-07-07.md`.

## Current guardrails

- Claims affecting an investment view require source/input evidence or an
  explicit gap.
- Deterministic code owns financial math; models interpret and verify.
- All HTTP goes through the polite scraper layer; parser changes need fixtures.
- No direct buy/sell advice, fabricated values, or hidden AI calls in dossier
  reads.
- Re-read `docs/project-guardrails.md` before and after substantial work.
