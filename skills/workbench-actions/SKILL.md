---
name: workbench-actions
description: Run explicit user-triggered Stock Analysis Workbench actions and explain the current operator flows. Use to start, stop, inspect, refresh Discover, add a company to Research, queue Research or valuation, synchronize/review Portfolio, or drain queued Codex work. Never create a recurring worker.
---

# Workbench actions

Reading never fetches a source, writes state, queues work, claims a lease, or
calls a model. Only the commands below may mutate durable state.

## Current flows

| User intent | Action | Durable result |
|---|---|---|
| Check the app | `./workbench doctor` then `./workbench status` | Read-only health report |
| Start or stop | `./workbench start` / `./workbench stop` | Local services only |
| Refresh Discover evidence | `POST /api/discovery/refresh` | One immutable source version; no Research job |
| Inspect Discover | `GET /api/discovery` | One `workbench_sieve_v1` state with coverage, survivors, exclusions and gaps |
| Add a company | `POST /api/research-cases` with ticker or eligible frozen Discover version | One company, one active case, at most one initial Research job |
| Inspect Research | `GET /api/research-cases` / `GET /api/research-cases/by-ticker/{ticker}` | Phase-aware list or one canonical snapshot workspace |
| Refresh company evidence | `POST /api/companies/{ticker}/refresh?scope=all` | Bounded stored evidence refresh; no snapshot or model result |
| Confirm/correct profile | `POST /api/research-cases/{id}/profiles` | Next immutable human-confirmed/corrected profile |
| Queue Research review | `POST /api/research-cases/{id}/review-runs` | One content-idempotent review job |
| Verify/save Research | Canonical `verify_research_snapshot` then `save_research_snapshot` adapters | One verifier-gated immutable v3 snapshot; terminal job |
| Open valuation | `GET /api/research-cases/{id}/valuation-workspace` | Read-only template and immutable valuation history |
| Preview human assumptions | `POST /api/research-cases/{id}/valuation-preview` | Zero-write deterministic comparison |
| Queue Codex valuation | `POST /api/research-cases/{id}/valuation-runs` | Valuation artifact frozen to Research/base inputs; Codex drafts assumptions/probabilities |
| Verify/save valuation | Canonical valuation verify then save adapters | Structurally gated immutable valuation; terminal job |
| Open Portfolio | `GET /api/portfolios/workspace` | Zero-write stored holdings, mappings, analytics and review history |
| Synchronize myfund | `POST /api/portfolios/sync/myfund` | Durable attempt and reused or next immutable snapshot |
| Correct mapping | `PATCH /api/portfolios/mappings/{id}` | Explicit current identity interpretation |
| Queue portfolio review | `POST /api/portfolios/review-runs` | One content-idempotent frozen review job |
| Drain queue | Invoke `$workbench-run-queue` | Lease recovery and repeated claim/verify/save until empty or a safety cap fires |

## Honest current limits

- Discover currently retains only the legacy market-rating source page. It is
  insufficient to execute the full Workbench exclusion/improvement rules, so
  the single sieve is `blocked`, has no fabricated survivors or exclusions,
  and names the missing market-factor batch. S1 supplies that batch.
- Company refresh and Research collection may retain forum material only as a
  labelled lead. Conclusions require permitted primary or normalized evidence.
- Research writes only `company-research-v3` / `research-snapshot-v3`.
  Historical snapshots remain readable; there is no legacy write path.
- Valuation queueing freezes the Research/base boundary. Scenario mechanisms,
  assumptions and probability rationales belong to the company-specific Codex
  draft; there are no default grids or probabilities.
- Portfolio reconciliation mismatches warn and identify affected figures. They
  never hide the whole dashboard. Operations import, auto-coverage and outcome
  scoring remain open Roadmap gates until their deterministic paths are green.

## Lifecycle and safety

1. `./workbench start` starts services and migrations only. It does not fetch,
   enqueue, or claim analysis work.
2. Add/reactivate Research through `/api/research-cases`; repeated content
   reuses the case and eligible job while preserving snapshots/history.
3. New Research review jobs require a human-confirmed/corrected profile with a
   company-specific source question and freeze the prior snapshot, current
   source state, complete profile, and fingerprints.
4. Research v3 records exactly one bounded issuer-primary,
   regulatory-primary, BiznesRadar, PortalAnaliz, and other-web attempt; every
   driver gets next-quarter and 12-month Outlook assessments and every frozen
   company question is resolved or retained as a named gap.
5. Valuation structural gates recompute math, validate probability structure,
   rationale/provenance, scenario completeness, company-specific vector
   distance, lineage, and drafter/verifier separation before judgment review.
6. Portfolio sync stores unknown instruments and reconciliation differences.
   Auto-produced coverage jobs must be idempotent, logged, and prioritized by
   position weight × staleness when S4 enables that producer.
7. `$workbench-run-queue` clears eligible work with lease recovery and bounded
   failure caps; it is not a recurring process.

Never request or store myfund login/password data, automate a provider web UI,
issue a buy/sell instruction, execute a transaction, use direct SQL for an
artifact save, or expose secrets. Update this skill, `CHANGELOG.md`, and
`docs/model-usage.md` whenever a UI/API/CLI/queue/source/analysis boundary
changes.
