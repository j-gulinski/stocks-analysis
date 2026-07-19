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
| Refresh Discover evidence | `POST /api/discovery/refresh` | One immutable all-page market-factor batch; no Research job |
| Inspect Discover | `GET /api/discovery` | One `workbench_sieve_v1` state plus any retained BiznesRadar expectation curves (levels, growth, count and range), at most 100 survivors, exclusions and gaps |
| Add a company | `POST /api/research-cases` with ticker, or `ticker` + typed frozen Discover `batch_id`/sieve version | One company, one active case, at most one initial Research job; Discover origin is server-recomputed and frozen |
| Inspect Research | `GET /api/research-cases` / `GET /api/research-cases/by-ticker/{ticker}` | Stored-state agenda plus phase-aware rows; current portfolio holdings lead by frozen weight × staleness priority and show subordinate holding context, source-backed next-report state, or one canonical Research → Valuation → History workspace |
| Refresh company evidence | `POST /api/companies/{ticker}/refresh?scope=all` | Bounded stored evidence refresh; a same-company parsed BiznesRadar profile date is retained as `report-calendar-v1`, then one future Research review may be created/reused only after all refreshed page versions are frozen; no snapshot/model call occurs in the request |
| Backfill statement publication dates | `cd backend && ./.venv/bin/python scripts/backfill_statement_publication_dates.py [--ticker TICKER]` | Additive/idempotent replay of stored parsed BiznesRadar financial-report `DocumentVersion.raw_content` into source-bound publication-date Facts; performs no HTTP and reports per-version parse failures |
| Authorize one blocked official PDF | `codex_ingest_issuer_ir_report.py --authorize-direct-official-url --ticker ... --url ... --title ... --authorization-reason ...` | One immutable exact-URL authorization claim, followed by the unchanged bounded PDF fetch; registered HTTPS issuer host and `.pdf` only |
| Confirm/correct profile | `POST /api/research-cases/{id}/profiles` | Next immutable human-confirmed/corrected profile; the latest stored report schedule is reconciled and may become eligible |
| Queue Research review | `POST /api/research-cases/{id}/review-runs` | One canonical review job idempotent for the prior snapshot, current source manifest and confirmed profile |
| Verify/save Research | Canonical `verify_research_snapshot` then `save_research_snapshot` adapters | One verifier-gated immutable v3 snapshot; terminal job |
| Open valuation | `GET /api/research-cases/{id}/valuation-workspace` | Read-only evidence→driver→forecast→value bridge, runway/reinvestment, Street bridge, five-period paths, independent method anchors, DCF sensitivity, reverse expectations and immutable valuation audit |
| Preview explicit advanced assumptions | `POST /api/research-cases/{id}/valuation-preview` | Zero-write five-year, multi-method deterministic comparison; API only |
| Queue Codex valuation | `POST /api/research-cases/{id}/valuation-runs` | Valuation frozen to Research/Street inputs; the queued Codex skill performs the company-specific causal analysis and drafts evidence-bound annual drivers, runway, capital allocation/net debt, terminal economics, method fit and conditional probability evidence; Python only validates and computes |
| Verify/save valuation | Canonical valuation verify then save adapters | Structurally gated immutable valuation; terminal job |
| Open Portfolio | `GET /api/portfolios/workspace` | Zero-write stored holdings, mappings, operation history/reconciliation, review history and typed `portfolio-performance-v1` TWR/XIRR evidence (status, value, method, window, timing, day count, terminal identity, flow count and gaps) |
| Synchronize myfund | `POST /api/portfolios/sync/myfund` | Durable attempt and reused or next immutable snapshot; one canonical resolver refreshes current mappings without rewriting frozen position rows, then atomically logs and queues/reuses eligible initial Research, Research review and valuation coverage by weight × staleness |
| Preview operations CSV | `POST /api/portfolios/operations/preview` with local filename/content | Zero-write parsing of the official full myfund history export; exact headers, optional times/source sequence, signs, units × price ± commission with tax kept separate, and a sequence-bound content fingerprint |
| Import operations CSV | `POST /api/portfolios/operations/import` with the same content/fingerprint and `confirm_full_export=true` | Atomically replaces prior CSV rows only; repeated identical content is idempotent, contribution flows are reconciled and ticker cost basis appears only when quantity and timestamp ordering reconcile; ambiguous date-only/equal-time buy/sell sequences remain unpublished |
| Correct mapping | `PATCH /api/portfolios/mappings/{id}` with company ticker or ignored flag plus rationale | Locked explicit current identity interpretation; a mislabeled row may bind to an existing GPW company, while creating a missing company still requires one exact terminal `Akcje GPW`/PLN identity; exact cash cannot be changed |
| Queue portfolio review | `POST /api/portfolios/review-runs` | One content-idempotent frozen review job |
| Drain queue | Invoke `$workbench-run-queue` | Lease recovery and repeated claim/verify/save until empty or a safety cap fires |

## Honest current limits

- Discover refreshes the declared immutable rating, C/Z, operating-margin,
  debt, revenue, net-profit and equity pages as one batch. It publishes only
  when every page parses; reads reuse the last complete batch. Turnover and
  raw-net-debt change and point-in-time trailing income are not yet exposed by
  this manifest, so A6/B5/A7 remain named coverage gaps and B4 starts after an
  earlier positive C/Z batch is at least 30 days old. The one potential score
  uses only mutually aligned, recent factor periods; stale survivors remain
  visible but unscored. Analyst expectations are shown for companies whose
  `/prognozy` evidence has been explicitly retained by a company refresh;
  absent consensus is a visible collection gap and never lowers rank.
  When a detailed report explicitly shows a material discontinued result,
  batch v6 uses source-bound continuing-operation net-profit growth and
  trailing C/Z. If the quarterly bridge is incomplete the affected score
  component is unavailable, not pessimistically imputed; raw and normalized
  values plus fact/document IDs remain visible. Normalized current C/Z is not
  compared with raw C/Z history.
- Company refresh and Research collection may retain forum material only as a
  labelled lead. Conclusions require permitted primary or normalized evidence.
- If an issuer index is temporarily blocked, an explicitly authorized exact
  official PDF URL may be frozen as discovery evidence. It does not count as
  report content: a Research claim still requires the bounded PDF fetch and
  parsed page locators. A 403 stops retries and leaves the primary channel
  unavailable.
- Research reads and writes only `company-research-v3` /
  `research-snapshot-v3`. The clean-baseline reset deletes older snapshots,
  verifier shapes and compatibility adapters; they are not presented as
  readable history.
- Valuation queueing freezes the Research/base boundary including BiznesRadar
  fiscal-year levels, growth, forecast counts and ranges. The draft must expose
  a five-year variance bridge, recurring/non-recurring split, P/E/EV/DCF
  methods, reverse expectations, explicit first-period stub timing, DCF
  sensitivity and conditional probability posture. Under the sole canonical
  `valuation-snapshot-v3` / `valuation-engine-v4` contract, the same named
  company drivers span bad/base/good/event and their five fiscal-period
  revenue, EBITDA-margin, depreciation, capex, NWC, tax and financing deltas
  must exactly reconcile the anchor/year-on-year forecast; terminal growth
  must equal explicit reinvestment × incremental ROIC. The UI leads with that
  potential bridge and makes the five-period path inspectable without leading
  on audit metadata. There are no default grids, direct unexplained percentages
  or current-price-derived target multiples. Missing data affects coverage
  only; an uncalibrated posture publishes neither scenario percentages nor a
  weighted value.
- Queue policy freezes an exact public Codex model and reasoning effort from
  the Architecture routing table. Requested and actual host identity remain
  separate; an unavailable host identity is never presented as a match.
- After any implementation changes one of these actions or its visible result,
  run `../verify-workbench-vision/SKILL.md` in the live in-app browser before
  marking the Roadmap gate accepted.
- Portfolio reconciliation mismatches warn and identify affected figures. They
  never hide the whole dashboard. Independent TWR uses consecutive daily
  provider value/contribution observations and excludes each end-of-day
  contribution delta before compounding. XIRR uses opening window value,
  dated contribution deltas and the current provider total on the exact
  snapshot date with ACT/365; it does not depend on position-row
  reconciliation. Missing days, alignment, terminal identity or a unique root
  are named gaps, never approximated. Mapping uses only strict cash identity,
  one unambiguous terminal GPW ticker or one normalized known-company name;
  ambiguity stays visible. A reasoned manual correction may bind a provider-
  mislabeled row only to an existing GPW company; it may create a missing
  company only from one exact terminal `Akcje GPW`/PLN identity. Identical sync
  may repair the current mapping but never rewrites the frozen position
  classification. Successful sync auto-coverage is deterministic, idempotent
  and logged; live sync #4 mapped 99.97% of portfolio value and produced six
  queued initial-Research jobs plus one honest profile blocker. Current-only
  scenario aggregation rejects fallback to an older verified valuation and
  never publishes an uncalibrated weighted value. Operation import requires a
  full, unfiltered CSV: preview is zero-write, confirmation replaces only CSV
  rows, and missing real history remains a named gap. Staleness/falsifier event
  producers outside sync, the real operations import, outcome scoring and the
  six cost-bearing Research jobs remain open; they are not run by page reads.
  SNT's stored BiznesRadar profile names its next report for 5 August 2026,
  but calendar automation is correctly blocked until Kuba confirms or corrects
  the current Codex-proposed profile.

## Lifecycle and safety

1. `./workbench start` starts services and migrations only. It does not fetch,
   enqueue, or claim analysis work.
   The destructive clean-baseline reset is a one-time Roadmap gate performed
   only after canonical code is finished; normal startup never drops data.
2. Add/reactivate Research through `/api/research-cases`; repeated content
   reuses the case and eligible job while preserving snapshots/history.
3. New Research review jobs require a human-confirmed/corrected profile with a
   company-specific source question and freeze the prior snapshot, current
   source state, complete profile, and fingerprints.
4. Research v3 records exactly one bounded issuer-primary,
   regulatory-primary, BiznesRadar, PortalAnaliz, and other-web attempt; every
   driver gets next-quarter and 12-month Outlook assessments and every frozen
   company question is resolved or retained as a named gap.
5. Valuation structural gates recompute method math, the evidence-bound
   driver-to-value bridge, terminal reinvestment identity and conditional
   probabilities; validate source semantics (including the ban on BR forward
   trading P/E as a target), unknown neutrality, method reconciliation,
   scenario completeness, company-specific vector distance, lineage, and
   drafter/verifier separation before evidence, mechanism, potential and
   probability judgment review.
6. Portfolio sync stores unknown instruments, reconciliation differences and
   provider daily history. Python alone computes the typed TWR/XIRR contract;
   frozen portfolio-review verification recomputes it rather than trusting
   labels or supplied values. The successful-sync coverage producer creates or
   reuses canonical jobs atomically, logs every inclusion/exclusion/blocker and
   prioritizes claims by numeric position weight × staleness with FIFO ties.
   Operations import first previews without writes, then requires explicit
   confirmation of the same full-export fingerprint; changing operations after
   a Portfolio review is queued invalidates that frozen review input.
7. Company refresh stores one schedule per immutable profile version. Eligible
   confirmed cases reuse the canonical Research review with a post-publication
   `available_at`; manual review accelerates the same job. A usable saved review
   queues canonical Valuation in the same transaction. A source gap, profile
   gate or valuation-input conflict stays visible and does not fabricate work.
8. `$workbench-run-queue` clears eligible work with lease recovery and bounded
   failure caps; it is not a recurring process.

Never request or store myfund login/password data, automate a provider web UI,
issue a buy/sell instruction, execute a transaction, use direct SQL for an
artifact save, or expose secrets. Update this skill, `CHANGELOG.md`, and
`docs/model-usage.md` whenever a UI/API/CLI/queue/source/analysis boundary
changes.
