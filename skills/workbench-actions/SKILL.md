---
name: workbench-actions
description: Run explicit user-triggered Stock Analysis Workbench actions and explain the current operator flows. Use when the user wants to start, stop, inspect, refresh Discover, add a company to Research, preview or queue a valuation, or execute one queued Codex job. Never create a recurring worker.
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
| Compare Discover sieves | `GET /api/discovery` | Three server-owned factor/coverage views; only sufficiently sourced sieves return candidates |
| Add a company | `POST /api/research-cases` with a ticker or frozen Discover version | One company, one active case, at most one initial-research job |
| Run queued research | Invoke `$workbench-run-queue` | Exactly one claimed and completed job |
| Open company research | `GET /api/research-cases/by-ticker/{ticker}` | Read-only profile, latest immutable snapshot and history |
| Verify claimed research | `verify_research_snapshot` or its JSON-in script | Independent verdict bound to the exact draft; job remains running |
| Save claimed research | `save_research_snapshot` or its JSON-in script | One verifier-gated immutable snapshot; terminal job and cleared lease |
| Open valuation | `GET /api/research-cases/{id}/valuation-workspace` | Read-only method/template state and immutable valuation history |
| Preview scenarios | `POST /api/research-cases/{id}/valuation-preview` | Zero-write deterministic quarter/year/price comparison |
| Queue valuation | `POST /api/research-cases/{id}/valuation-runs` | At most one content-identical `stock-company-valuation` job |
| Verify claimed valuation | `verify_valuation_snapshot` or `codex_verify_valuation_snapshot.py` | Independent exact-draft verdict and final probabilities; job remains running |
| Save claimed valuation | `save_valuation_snapshot` or `codex_save_valuation_snapshot.py` | One immutable valuation snapshot; terminal job and cleared lease |

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
4. Discover always compares the three typed sieve contracts. The
   financial-health sieve is a preliminary filter; do not describe Altman or
   Piotroski values as a recommendation. Its v1 membership thresholds
   (Altman `>= 8`, Piotroski `>= 7`) belong to the server contract, not the UI.
   Keep OBS and Portal Analiz candidates blocked while their server-provided
   market-wide coverage is incomplete.
   Company-level research rows never substitute for a market-wide sieve.
5. The browser may enqueue one durable job after an add, but it never executes
   or claims it. Do not add portfolio positions or make a trade decision.

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

## Capability maintenance

When a user-visible UI, API, CLI, queue, source, or analysis boundary changes,
update this skill in the same patch. Also update `CHANGELOG.md` and the concise
model-usage ledger, then verify the affected API and browser outcome.
