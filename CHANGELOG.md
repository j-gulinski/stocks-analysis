# Changelog / decision log

Durable decisions and completed slices only. `TASKS.md` owns current status;
implementation detail lives in stage plans, validation notes, archives and git.

## 2026-07-10 · Clarified model-routing scope

GPT-5.3 is now reserved for testing/mechanical work. Luna medium is the
default for basic bounded implementation; Terra high remains the default for
ordinary implementation, and Sol is reserved for complex or decision-critical
work. Earlier ledger rows remain historical records, not active routing rules.
The stronger suitable model now runs at its full appropriate reasoning level;
quality or reasoning is not lowered for an assumed budget limit. The ledger
records the selected pair and any host substitution or escalation.

## 2026-07-10 · Scenario company outcomes

Scenario rows now include an explicit company-side condition: result under
pressure, stable result or improving result, with the relevant driver named as
EPS/zysk na akcję, value per share or EBITDA. The copy states that these are
qualitative conditions for analysis and that the current target price remains
the existing multiple-only calculation; priced operating-driver equations stay
deferred to RT.4.

## 2026-07-10 · Refined RT4 next task

The next implementation target is now RT4.1a: establish the durable
`ResearchCase` root with explicit state, current step and `as_of` before adding
priced operating-driver equations. This preserves the roadmap order and keeps
forecast/scenario persistence out of scope until the case contract is verified.

## 2026-07-10 · RT4.1a ResearchCase root

Added migration `0016` and a durable `ResearchCase` root keyed by company and
purpose. The API supports explicit workflow state, current step, `as_of` and a
named blocked reason, with purpose-scoped reads/updates and duplicate-safe
creation. Forecast and scenario persistence remain deliberately separate until
the case root is exercised by the next RT4 slice.

## 2026-07-10 · RT4.1b case header visibility

The company header now reads the purpose-scoped `ResearchCase` without creating
one on page load, shows its workflow state when present, and offers an
explicit `Utwórz przypadek` action when absent. State/step editing and brief
composition landed in the following RT4.1c slice.

## 2026-07-10 · RT4.1c case workflow editing

Added an explicit case editor for workflow state, current step and blocked
reason. The report brief now names the selected case step so the deterministic
read is anchored to the current research task; case state is never advanced
automatically. Creation and update failures remain visible in the page.

## 2026-07-10 · Explore ranking rationale and stale-analysis queue

Explore candidates now show their source rank, deterministic tie-break order,
BiznesRadar rating and Piotroski contribution in a per-row disclosure. An
explicit `force=true` source refetch schedules at most 15 top-ranked quick
analyses when the stored company has no analysis or its latest analysis is more
than seven days old. Recent, pending and not-stored candidates are counted in
the response; unknown source candidates are skipped rather than creating
companies or changing the watchlist automatically. The queued run carries the
source document version and requires `verifier_strict` before any result can be
approved.

## 2026-07-10 · RT2.3 ESPI evidence bridge

Completed the first RT2.3 slice without a schema change: detail-enabled GPW
ESPI/EBI polling now records or reuses an immutable `DocumentVersion` and adds
an `Event` with explicit, unverified claim locators for the report title and
subject. Metadata-only polling remains incomplete and does not manufacture an
evidence document. Existing `EventReport` rows remain the serving interface.

## 2026-07-10 · Explore queued-ticker visibility

The post-refetch Explore notice now lists the exact tickers accepted into the
stale-analysis queue, alongside recent, pending and not-stored skip counts.
This keeps the scheduling action auditable without implying that a model has
already run.

## 2026-07-10 · IL.3 explicit falsifiers

Added migration `0013` and company-linked falsifiers with explicit
`holding`/`warning`/`fired` states. Every transition requires a human/evidence
reason; metrics and models never infer a fired state. The research queue now
orders fired cases before warnings, and the company report exposes a compact
editor with visible status and review date.

## 2026-07-10 · IL.5 UI alignment verification

Verified the company read as four canonical tabs: Report, Charts, Sources and
Codex. Desktop and 390px mobile screenshot checks found no page overflow; fresh
DOM-grounded tab interactions loaded the Sources audit view and Codex review
view. The task is complete; the next queue remains in RT.1/RT.2.

## 2026-07-10 · CX.15d opt-in polling boundary

Documented the existing pre-session script as the only supported periodic
entrypoint. Scheduling is disabled by default and may poll/queue only after
complete ingestion; it cannot claim work, call a model or approve output.
Hosted use requires private deployment controls and never receives personal
Codex/provider credentials.

## 2026-07-10 · CX.16a frozen cohort

Created the first research-only cohort manifest with one documented hit (DGN),
one documented miss (Suntech), one unmeasured control candidate (OPTEX) and one
excluded unverified placeholder (SNT). No delisting was found in the stored
corpus. Selection, identity, publication availability and corporate-action
limits are recorded; no replay or performance claim is permitted yet.

## 2026-07-10 · CX.16b availability caveat

Extended the deterministic backtest availability metadata so
`estimated_period_lag` runs persist an explicit restatement caveat in run
parameters, known inputs and data-quality summaries. The mode remains
research-only and `needs-human`; original filing versions and historical case
identity are still open.

The local coverage audit found no stored company, price or report rows for DGN,
OPTEX or SUNTECH; current SNT fixture data is not admitted as the unverified
historical case. This is an evidence-backed `needs-human` boundary, not a
failed replay.

## 2026-07-10 · CX.11 price availability boundary

Added migration `0015` with nullable `prices.scraped_at`, populated by price
refreshes and exposed in the API. Strict deterministic backtests now exclude a
price learned after its observation date or with unknown availability; older
rows remain unknown until refreshed. Financial version lineage and sufficient
historical depth are still open.

## 2026-07-10 · CX.16c deterministic-only scoring marker

Backtest runs now persist `scoring_policy=deterministic_prescore_only` and
`ai_refined_output_included=false` in parameters and summaries. This makes the
current prescore boundary auditable; thesis/scenario replay remains deferred
until the cohort has point-in-time inputs.

Independent `verifier_strict` review of the live SNT probe returned
`needs-human`: the run has no observations because historical price
availability is unknown, remains `verification_status=pending`, and is not
eligible for approval or strategy learning.

## 2026-07-10 · CX.13 empty evaluation guard

An agent-valuation evaluation with no saved `analysis_runs` now returns
`needs-human` and an explicit no-evidence warning instead of `pending`.
Structured predictions remain the only scored input; prose is never inferred.

## 2026-07-10 · IL.4 read-only position context

Added migration `0014` for a position ledger containing ticker, entry, size,
quantity and sizing-rule context. Positions are read-only to analysis and AI.
CSV import pins one portfolio, requires explicit ticker mapping, surfaces
unmatched rows and is idempotent. The documented official API endpoint is now
implemented behind the same polite HTTP boundary with no key in errors/logs.
The live local call reached myfund but returned a remote error, sanitized to
HTTP 502; no position was imported and the external sync remains needs-human.

## 2026-07-10 · Active documentation compaction

Reduced `PLAN.md`, the canonical research-platform plan and the changelog to
compact architecture/contracts, current decisions and pointers. Preserved
binding guardrails, stable task IDs, RT order, source/evidence invariants,
model-routing rules, acceptance notes and historical recovery through archives
and git.

## 2026-07-10 · Decision loop and routing policy

- IL.1: migration `0011`, append-only decision journal, confidence/thesis/
  invalidation/next-check/review date and hashed thesis snapshot.
- IL.2: migration `0012`, deterministic dossier/event monitor snapshots and one
  immutable change card per changed baseline; no scraper or model call in diff.
- CX.15c: ESPI re-check and one queue-claim UI actions. Claiming stops at the
  durable `running` boundary; Codex owns the workflow and strict save.
- Model strength and reasoning are separate. A stronger model may use one lower
  reasoning step for bounded work; maximum reasoning remains for financial
  policy, security, look-ahead and other decision-critical tasks.
- Model ledger now records routing, role, concrete-host disclosure and
  verification per session.

## 2026-07-10 · Documentation lifecycle

`AGENTS.md` is authoritative. `TASKS.md` is the only live queue. The compact
`PLAN.md` is a stable architecture map; `docs/plan-research-platform.md` is the
binding RT roadmap. Closed detail is retained in `docs/archive/`, validation
notes, learning notes and git rather than repeated in active documents.

## 2026-07-10 · Session-driven Codex operation

CX.15a/15b added the ESPI watermark, bounded pagination, completeness gating,
idempotent detached startup hook and one durable queue claim. Incomplete live
polls never queue work; source latency does not hide application health.

## 2026-07-10 · Evidence, report and hosting boundaries

The company workspace is report-first: deterministic facts/calculations,
scenarios, evidence audit and separately labelled Codex review. UI-visible
model output requires strict verification. Local queue execution is supervised;
personal Codex credentials are not embedded in hosted infrastructure.

## 2026-07-09 · CX / RT foundation

Added provider-neutral runs, JSON/MCP contracts, ESPI events, durable queue
lifecycle, evidence/run provenance, deterministic replay and the local
`workbench` operator/research skill.

## 2026-07-08 · Thesis and scenarios

Completed source-grounded generic thesis/strategy data, Malik profile,
deterministic-first refinement and validation; then negative/base/positive
scenario sensitivity, bounded valuation support, corpus enrichment and
validation. Detailed stage notes remain in the historical plans.

## 2026-07-07 · First vertical slice

Established the FastAPI + Next.js workbench, PostgreSQL/SQLite test split,
polite BiznesRadar/PortalAnaliz ingestion, metrics, forecast, dossier,
watchlist, stock pages, forum support and initial strategy/AI contracts.

## Permanent guardrails

- Claims influencing an investment view need evidence, an input field or an
  explicit gap.
- Deterministic code owns financial math; models interpret and verify.
- All HTTP uses the polite scraper boundary; parser changes need fixtures.
- No fabricated values, hidden AI on reads or direct buy/sell advice.
- UI output shows draft/verified/rejected/needs-human status.
