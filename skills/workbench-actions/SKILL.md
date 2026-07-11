---
name: workbench-actions
description: Run explicit user-triggered Stock Analysis Workbench actions and explain the current operator flows. Use when the user wants to start, stop, inspect, refresh Discover, add a company to Research, or execute one queued Codex job. Never create a recurring worker.
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
| Add a company | `POST /api/research-cases` with a ticker or frozen Discover version | One company, one active case, at most one initial-research job |
| Run queued research | Invoke `$workbench-run-queue` | Exactly one claimed and completed job |

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
3. The financial-health sieve is a preliminary filter. Do not describe Altman
   or Piotroski values as a recommendation. Keep OBS and Portal Analiz sieves
   unavailable until their declared market-wide facts exist.
4. The browser may enqueue one durable job after an add, but it never executes
   or claims it. Do not add portfolio positions or make a trade decision.

## One queued Codex job

Use `$workbench-run-queue` only after an explicit request. It recovers expired
leases, claims at most one row, follows that row's skill/model contract,
heartbeats, obtains independent strict verification, saves to the same
`agent_run_id`, and stops. An empty queue is a successful no-op.

## Capability maintenance

When a user-visible UI, API, CLI, queue, source, or analysis boundary changes,
update this skill in the same patch. Also update `CHANGELOG.md` and the concise
model-usage ledger, then verify the affected API and browser outcome.
