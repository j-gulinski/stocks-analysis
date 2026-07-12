---
name: workbench-actions
description: Run explicit user-triggered Stock Analysis Workbench actions and explain the current operator flows. Use when the user wants to start, stop, inspect, refresh Discover, add a company to Research, preview or queue a valuation, synchronize/review Portfolio, or execute one queued Codex job. Never create a recurring worker.
---

# Workbench actions

Use only explicit commands. Reading a screen never fetches a source, writes
state, queues work, claims a lease, or calls a model.

## Current flows

| User intent | Action | Durable result |
|---|---|---|
| Check the app | `./workbench doctor` then `./workbench status` | Read-only health report |
| Start or stop | `./workbench start` / `./workbench stop` | Local services only; no queue claim |
| Refresh Discover | `POST /api/discovery/refresh` | One stored source snapshot; no research jobs |
| Inspect Discover | `GET /api/discovery` | Three server-owned status/coverage views plus the sourced financial-health candidate list |
| Add a company | `POST /api/research-cases` with a ticker or frozen Discover version | One company, one active case, at most one initial-research job |
| Run queued research | Invoke `$workbench-run-queue` | Exactly one claimed and completed job |
| Open company research | `GET /api/research-cases/by-ticker/{ticker}` | Read-only profile, latest immutable snapshot and history |
| Refresh existing Research | `POST /api/research-cases/{id}/review-runs` | One content-idempotent company-review job bound to the prior snapshot and queued source state |
| Verify claimed research | `verify_research_snapshot` or its JSON-in script | Independent verdict bound to the exact draft; job remains running |
| Save claimed research | `save_research_snapshot` or its JSON-in script | One verifier-gated immutable snapshot; terminal job and cleared lease |
| Open valuation | `GET /api/research-cases/{id}/valuation-workspace` | Read-only method/template state and immutable valuation history |
| Preview scenarios | `POST /api/research-cases/{id}/valuation-preview` | Zero-write deterministic quarter/year/price comparison |
| Queue valuation | `POST /api/research-cases/{id}/valuation-runs` | At most one content-identical `stock-company-valuation` job |
| Verify claimed valuation | `verify_valuation_snapshot` or `codex_verify_valuation_snapshot.py` | Independent exact-draft verdict and final probabilities; job remains running |
| Save claimed valuation | `save_valuation_snapshot` or `codex_save_valuation_snapshot.py` | One immutable valuation snapshot; terminal job and cleared lease |
| Open Portfolio | `GET /api/portfolios/workspace` | Zero-write latest stored snapshot, mappings, analytics and review history |
| Synchronize myfund | `POST /api/portfolios/sync/myfund` | One durable attempt and either reused or next immutable snapshot |
| Correct a mapping | `PATCH /api/portfolios/mappings/{id}` | Explicit current interpretation; an exact confirmed PLN `Akcje GPW` `(CODE)` may create only a minimal Company identity |
| Queue portfolio review | `POST /api/portfolios/review-runs` | At most one content-identical `stock-portfolio-review` job |
| Verify portfolio review | `codex_verify_portfolio_review.py` | Independent verdict bound to the exact frozen draft |
| Save portfolio review | `codex_save_portfolio_review.py` | One immutable review; terminal job and cleared lease |

## Current capability limits

- Discover currently produces candidates only from the financial-health sieve.
  OBS and Portal Analiz expose honest source/factor gaps but no candidates,
  while the UI renders the same per-sieve candidate/overlap contract for all
  three columns. Do not describe the empty blocked columns as live comparison
  or market-wide coverage.
- `assess_data_readiness` and `codex_candidate_scan.py` measure stored-company
  data readiness, not investment potential; do not present their score as a
  stock opportunity rank.
- Discover reads expose the immutable source version separately from the last
  successful source check and the latest failed refresh. A stale list remains
  inspectable but does not show a current rank. WIG bucket, sector, and size
  stay explicit unknowns until sourced; opening Discover still performs no
  fetch, write, queue, or model call.
- Malik/OBS has a source-grounded Codex lens and the only ready Valuation pack;
  its market-wide Discover sieve and canonical persisted/rendered Research
  perspective remain planned. Areczeks and Elendix stay draft until retained
  sources and stage-specific inputs satisfy the Strategy contract. Never
  simulate their company conclusions or blend methods implicitly.
- The current company overlay is model-proposed and read-only. User-confirmed
  profile versioning and the Research `Do sprawdzenia` agenda are Roadmap work,
  not current actions.

Research lists `ResearchCase` rows, not watchlist membership. Removing a
watchlist item never deletes the company, evidence, case, analysis, or history.

## Lifecycle

1. Run `./workbench doctor`; it must not print secret values.
2. For a start/open request, run `./workbench start` (or `--open`) and then
   `./workbench status`.
3. `start` only starts the local services and migrations. It does not fetch
   evidence, enqueue analysis, or claim Codex work.
4. `./workbench stop` stops Workbench-owned backend/frontend processes and
   leaves PostgreSQL running.

## Discover and Research

1. Use stored Discover evidence for reads. Refresh the BiznesRadar snapshot
   only when the user asks or presses the explicit refresh control.
2. Add through `/api/research-cases`. Repeated requests reuse the case and its
   stable initial job. Report the visible state honestly: waiting, collecting,
   provisional, verified, rejected, or needs intervention.
3. The company page renders versioned `research-snapshot-v1`/`v2` artifacts as
   the canonical six-section workspace when one exists. The prior dossier
   remains a labelled secondary audit view and cannot override snapshot status.
4. Discover shows status and coverage for three typed sieve contracts, but only
   the financial-health sieve currently supplies candidate rows. Do not claim
   per-sieve candidate comparison or overlap yet, and do not describe Altman or
   Piotroski values as a recommendation. Its v1 membership thresholds
   (Altman `>= 8`, Piotroski `>= 7`) belong to the server contract, not the UI.
   Keep OBS and Portal Analiz candidates blocked while their server-provided
   market-wide coverage is incomplete.
   Company-level research rows never substitute for a market-wide sieve.
5. The browser may enqueue one durable job after an add, but it never executes
   or claims it. Do not add portfolio positions or make a trade decision.
6. An existing case with a snapshot may explicitly queue `stock-company-review`.
   The command freezes the prior snapshot/artifact and current latest source
   identities, reuses an identical job, and rejects a competing active Research
   collection. Reads never queue it. The prior snapshot remains canonical until
   the claimed worker collects evidence, obtains a separate strict verdict and
   saves the next sequential snapshot.
7. Bounded issuer-IR collection includes ASBIS, Artifex Mundi, Digital Network,
   CD PROJEKT, cyber_Folks, Benefit Systems and Creotech official report pages.
   Report links are extracted only from
   issuer-specific content (`.ncont-content` / `.investors-page-content` /
   `.files-section` / `.presstype-quarter .entry-content` / `.attachments` /
   `.news-related-files` / `.investors-content__report`);
   same-host empty redirects may be upgraded from HTTP to HTTPS, but the final
   PDF connection must still pass public-host and connected-peer checks. This
   collection is a worker action, never a Research GET side effect.

## One queued Codex job

Use `$workbench-run-queue` only after an explicit request. It recovers expired
leases, claims at most one row, follows that row's skill/model contract,
heartbeats, obtains independent strict verification, saves to the same
`agent_run_id`, and stops. An empty queue is a successful no-op.

## Valuation

1. Start only from a `provisional` or `verified` Research snapshot and an
   available company-archetype template. Reads and previews never queue or
   claim work.
2. The user edits the three typed `negative`, `base`, and `positive` scenarios.
   Template seeds are labelled working human assumptions, never source facts.
   Only `malik_obs_v1` is ready; Areczeks and Elendix stay visibly blocked.
3. Preview through `/valuation-preview`. Python owns every financial, cash-flow,
   per-share, and price calculation. A non-positive forward EPS has no P/E
   price; own-history reversion remains a separate labelled sensitivity.
4. Queue only after the explicit user action. The job freezes Research/source/
   fact/price/scalar identities, assumptions, deterministic outputs and both
   fingerprints. Repeating identical content reuses the same job.
5. `$company-valuation` processes exactly one claimed job. A distinct
   `verifier_strict` context owns final probabilities and status. Any named
   upstream or scalar-lineage gap caps a passing result at `provisional`.
6. Saving must attach only the verification ID to the unchanged draft. It
   creates one immutable `ValuationSnapshot`, clears the lease, and never
   recommends or executes a trade.

## Portfolio

1. Opening `/portfolio` or `GET /api/portfolios/workspace` reads only the last
   stored state. Synchronize only after the user's explicit action. Use the
   configured API key and exact single portfolio name; never request or store
   a login/password and never automate the myfund web UI.
2. Every sync attempt is recorded. Identical content reuses the latest
   snapshot; changed content receives the next version. Preserve unknown rows
   and surface reconciliation gaps. A failed refresh leaves the last good
   snapshot visible.
   If retained rows do not reconcile to the provider total, withhold all
   derived concentration, coverage, liquidity, risk, scenario and review
   output. Keep only the provider summary, partial-history status and raw rows.
3. Mapping correction is explicit and cannot reinterpret an exact cash/company
   identity. A confirmed ticker must equal the one unambiguous terminal `(CODE)`
   on a PLN `Akcje GPW` provider identity. The correction reuses an existing
   Company or creates only that minimal GPW identity; it creates no ResearchCase
   or job, and a user-confirmed mapping remains correctable. Company analysis
   and valuation never change because a position is owned or sized differently.
   Sequential `0..N-1` myfund object keys are collection positions, not native
   instrument IDs. `Konta gotówkowe` is an exact cash type. Snapshot cost/result
   are complete current-position sums or an explicit gap; flow-aware provider
   profit/contribution remains provider-labelled history. Portfolio reads expose
   the canonical Company ticker separately from the provider label so links
   always open the mapped Research identity.
4. Treat return and benchmark series as provider-reported. TWR/XIRR and total-
   return benchmark claims remain unavailable without independently reconciled
   dated flows and benchmark semantics. Liquidity remains a labelled 20-session
   raw-series estimate.
5. Aggregate only verified valuations bound to the latest point-in-time
   Research snapshot. Keep uncovered value unchanged and label aligned
   downside/base/upside as simultaneous sensitivity, not joint probability.
6. Queue review only through `/portfolio/review-runs`. `$portfolio-review`
   reads the frozen snapshot/mappings/analytics/valuation identities, never
   syncs or repairs them, obtains an independent strict verdict, and saves the
   unchanged Polish draft through the canonical scripts. It never recommends
   a transaction.
7. Risk context freezes point-in-time Research/Profile and visibly current-
   only falsifier timing. A shared sector/archetype group is co-exposure, not
   correlation, covariance or joint probability. Historical liquidity may use
   only price rows learned by the portfolio snapshot cutoff.

## Capability maintenance

When a user-visible UI, API, CLI, queue, source, or analysis boundary changes,
update this skill in the same patch. Also update `CHANGELOG.md` and the concise
model-usage ledger, then verify the affected API and browser outcome.
