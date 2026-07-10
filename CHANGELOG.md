# Changelog / decision log

Durable decisions and completed slices only. `TASKS.md` owns current status;
implementation detail lives in stage plans, validation notes, archives and git.

## 2026-07-10 · Clarified model-routing scope

GPT-5.3 is now reserved for testing/mechanical work. Luna medium is the
default for basic bounded implementation; Terra high remains the default for
ordinary implementation, and Sol is reserved for complex or decision-critical
work. Earlier ledger rows remain historical records, not active routing rules.

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
