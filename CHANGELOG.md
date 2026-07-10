# Changelog / decision log

Durable decisions and completed slices only. `TASKS.md` owns current status;
implementation detail lives in stage plans, validation notes, archives and git.

## 2026-07-11 · RT5.6 strict scenario-simulation persistence boundary

The typed MCP save/verify path now permits a `scenario-simulation` run to reach
`pass` only when the deterministic scenario snapshot passes its own verifier,
the priced-outcome gate is approved, the input snapshot carries the matching
operating-bridge fingerprint, and an independent `verifier_strict` result
passes representative coverage, no-look-ahead, math, source-lineage and input
match checks. Draft and `needs-human` runs remain saveable. A stale bridge is
rejected before the analysis or verification row is committed, so a previous
approval cannot silently unlock changed inputs. This is an audit boundary, not
an OpenAI provider implementation; RT5.1–RT5.3 remain open.

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

## 2026-07-10 · RT4.3a approved-assumption context bridge

Approved case-linked assumption sets now flow into the dossier's scenario
context with their per-item provenance intact. Draft and rejected sets stay
out of UI-visible scenario output, and the scenario panel labels the context
as non-priced so the current deterministic multiple valuation cannot be
silently changed. RT4.3b remains the separate step for mapping approved driver
keys into tested operating equations and valuation sensitivity.

## 2026-07-10 · RT4.3b deterministic driver sensitivity

Added a pure, typed overlay for approved case drivers already understood by
the valuation engine: EPS, book value, EBITDA TTM, share count and net cash.
The dossier keeps its base multiple valuation unchanged and exposes separate
sensitivity rows with baseline, projected and delta values. Draft/rejected
sets, unsupported keys and model suggestions remain visible as inactive
inputs; a model suggestion must be explicitly converted to evidence or a human
assumption before it can affect the deterministic what-if result. Template
operating equations remain the next RT4.3c slice.

## 2026-07-10 · RT4.3c industrial/consumer operating bridge

Added the first bounded company-template equation using the existing pure
forecast service: revenue, gross margin, selling/admin and other P&L drivers
flow through projected net profit/EPS or EBITDA and a transparent C/Z or
EV/EBITDA bridge. The dossier compares operating target price with the current
multiple-only baseline. Only industrial and consumer archetypes are supported
in this pilot; unsupported sectors remain explicit. Cash conversion, working
capital and capex are deferred to RT4.3d rather than inferred.

## 2026-07-10 · RT4.3d cash-conversion readiness (partial)

Added canonical cash-flow field mapping for operating CF, investing CF,
financing CF and capex, plus a dossier readiness snapshot showing CF/net-profit
conversion and capex intensity when comparable periods exist. The UI keeps the
working-capital gap explicit: receivable/inventory changes are not inferred
from one balance snapshot. RT4.3d remains open until that source-backed bridge
is implemented and tested.

The second RT4.3d pass now maps current/non-current receivables and inventory
from comparable balance periods, exposing their change and cash effect beside
CF and capex. It still does not feed a projected FCF price; that final bridge
remains open and is not inferred from the snapshot.

The final RT4.3d pass adds a separate P&L-to-FCF bridge for approved operating
scenario rows: projected net profit + depreciation + measured working-capital
cash effect + capex. Historical FCF remains `operating CF + capex` and is not
adjusted by working capital a second time. No FCF price lens is introduced;
that remains a future, separately approved valuation method.

## 2026-07-10 · RT4.3e explicit FCF valuation lens

Added an optional FCF/share × explicit FCF-multiple lens. It requires approved
`capex`, `working_capital_change` and `fcf_multiple` inputs with non-model
provenance; incomplete, suggested or negative-FCF cases stay `needs-human`.
The lens reports its price and delta beside the existing multiple valuation and
never replaces that baseline automatically.

## 2026-07-10 · RT4.4a priced-outcome verifier gate

Priced company outcomes are now attached only when the separate FCF lens is
applied and the latest persisted `verifier_strict` run passes representative
industrial, financial and event-driven coverage, no-look-ahead, math
reconciliation and source-lineage checks. Missing or incomplete verification
keeps the existing qualitative company outcome and exposes the blocked reason
in the dossier/UI. No migration was needed; the safer default is to remain
qualitative until a persisted analysis-linked verification run exists.

## 2026-07-10 · RT4.5b priced-outcome gate checklist

The scenario panel now shows each required priced-outcome check separately:
industrial/financial/event-driven coverage, no look-ahead, math reconciliation
and source lineage. Missing evidence is labelled `oczekuje`, partial evidence
is not promoted to pass, and an approved gate remains the only path that
changes the company outcome from qualitative to priced. Representative
persisted verifier cases remain the open acceptance item.

The RT4.5b API test now covers the full promotion path with fixture-only
`AnalysisRun`/`VerificationRun` records: complete checks promote the base row
to `mode: priced`, while production still requires real persisted evidence.

The gate now also hashes the exact deterministic operating bridge and requires
the strict verifier to return that fingerprint. A valid verifier result for an
older or otherwise different input bridge therefore remains blocked.

Only a verifier linked to the dedicated `scenario-simulation` workflow can now
unlock priced outcomes; quick/deep company-analysis verification is not reused
for this decision-sensitive scenario contract.

Added a deterministic simulation verifier to the dossier/UI. It checks unique
scenario IDs, required kinds, finite numbers, probability ranges and sum,
weighted price/upside reconciliation, row upside, qualitative outcome mode and
safety framing. The weighted engine now returns no unconditional EV when a
positive-probability scenario lacks a target price; `priced_probability_mass`
and a human-review status make that gap explicit. Live SNT verification is
`math_passed` (419.22 PLN / 12.03% reconciled), while strict priced approval
remains blocked by the unsupported biotech template and missing persisted
scenario verifier.

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

## 2026-07-10 · RT4.2a assumption-set contract

Added migration `0017` and a case-linked `AssumptionSet` contract for
negative/base/positive/event scenarios. Each input stores a required
provenance label (`evidence`, `human_assumption`, or `model_suggestion`),
optional source reference, rationale and unit; the API keeps sets scoped to a
research case and records the forwarded editor identity. This is the durable
input boundary only; the scenario editor, step history and priced operating
equations remain subsequent slices.

## 2026-07-10 · RT4.2b assumption editor

The Scenarios workspace now reads saved case-linked assumption sets and offers
a compact editor for scenario kind, label, value, unit, provenance, source
reference and rationale. New sets are deliberately saved as drafts and shown
with their provenance; this surface does not calculate target prices or
silently approve model suggestions. Appendable case-step history remains the
next workflow slice.

## 2026-07-10 · RT4.2c case-step history

Added migration `0018` and an append-only case-step history ledger. State or
current-step transitions now require a named reason and record the previous and
next workflow values plus the forwarded editor identity; blocked-reason-only
edits do not create a false transition. The company editor exposes the latest
history entries, while pre-existing cases remain history-empty rather than
receiving fabricated backfill events.

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
