# Pivot roadmap

This is the only live delivery document. It records outcomes and gates, not
session logs or a catalogue of every historical task. Git and `CHANGELOG.md`
retain completed detail.

## Current state

P0 is complete: the product/docs were reset, reads are side-effect free,
recurring project automations were removed, and company memory is
non-destructive. The P1 entry slice is green: Discover and typed-ticker adds
create/reuse/reactivate one visible case and one unclaimed initial job. P1 is
still open because the typed `CompanyProfile`/`ResearchSnapshot`, save gate,
tailored renderer, and first verifier-labelled pilot do not exist yet.

Current delivery focus: **finish P1's real research artifact**, then expand it
into the P2 archetypes and evidence-backed sieves.

| Stage | Outcome | Exit gate | Status |
|---|---|---|---|
| P0 · Reset | Four binding docs, obsolete artifacts removed, reads side-effect free, memory non-destructive, worker-only claims | tests prove zero-write reads, proxy verbs, archive preservation, no orphan claim | complete |
| P1 · Research vertical | one `Dodaj do Research` command creates/reuses a company and case and one executable initial job | candidate and ticker paths are idempotent; case appears immediately; one pilot reaches a verifier-labelled snapshot | in progress |
| P2 · Tailored research + sieves | common research spine, 2–3 real archetype packs, company overlay, primary-source plan, honest OBS/PA sieves | three comparable factor/coverage views; two representative companies render different relevant sections | waiting for P1 |
| P3 · Valuation | separate method packs, driver assumptions, deterministic quarter/year and price bridges | one industrial plus one non-industrial pilot reconcile and pass strict verification; sensitivity is labelled | waiting for P2 |
| P4 · Portfolio | dated myfund/API snapshots, mappings, history, deterministic portfolio analytics and scenario aggregation | repeated sync updates positions; history/benchmark reconcile; portfolio review cites verified company snapshots | waiting for P3 |
| P5 · Calibration | official adjusted returns, historical availability, mixed/holdout cases and method calibration | replay is no-look-ahead, reproducible, benchmark-relative, and reports calibration limits | waiting for data |

## P0 acceptance

- `GET /discovery` reads a stored snapshot and creates no `AgentRun`, company,
  or case. Source refresh is a separate explicit command.
- Startup/session hooks and UI do not claim Codex leases.
- The Next proxy supports every API method used by the client, including PATCH.
- Hiding/unpinning a company never deletes evidence or analysis history.
- Direct provider calls during refresh are disabled; model work is a durable
  job.
- Old mockups, screenshots, previews, archives, superseded plans, duplicate
  prototypes, generated build state, and task diary are removed.

## P1 acceptance

- One atomic, idempotent API accepts a frozen Discover candidate reference or a
  typed ticker.
- It resolves/creates `Company`, creates/activates `ResearchCase`, and queues
  exactly one `stock-initial-research` job with `company_id` and the
  `company-research` skill contract.
- A duplicate click returns the same case/job; no duplicate queue rows.
- Research lists cases, not watchlist rows, and displays the job as waiting,
  collecting, provisional, verified, rejected, or requiring intervention.
- The queue model policy and picker return an executable contract; only the
  executing worker claims, heartbeats, and completes it.
- The first result stores a source manifest, common research spine, selected
  archetype, company-specific drivers/questions, gaps, and strict verifier
  status.
- Browser QA proves Discover candidate -> Add -> immediate Research presence,
  direct ticker add, duplicate add, and case PATCH.

## P2 design boundary

Build the financial-health sieve first from one stored BiznesRadar universe
page. Add OBS and PortalAnaliz sieves only after bounded bulk factor pages or
equivalent sourced data provide their declared inputs. Each sieve returns
`id/version`, candidate coverage, top contributing factors, neutral metadata,
source references, and gaps; cap the visible result to a useful shortlist.

Research snapshots use a fixed schema plus versioned archetype/company profile.
P1 first adds their model/migration, schema validator, version/hash-frozen job
contract, save adapter, fixed renderer, and one verified/provisional pilot. P2
then broadens only from actual pilot needs, not every sector. Raw reports, OCR,
ESPI/EBI, issuer IR, and forum leads are source-plan items with explicit
completeness.

## P3 design boundary

Codex chooses/explains drivers and probabilities; deterministic services own
financial and price calculations. Preserve an immutable valuation snapshot and
separate strict verification. Backtesting remains a calibration gate, not a
marketing claim.

## P4 design boundary

Verify myfund's available API/export and terms before expanding ingestion. Sync
is snapshot/upsert with instrument mapping, not append-only de-duplication.
Company analysis stays independent of position size; portfolio aggregation
consumes only verified company scenarios.

## Verification commands

```text
./workbench doctor
cd backend && ./.venv/bin/pytest
cd frontend && npm run build
./workbench start
./workbench status
```

Run focused contract tests before the full suites and finish each active stage
with one browser interaction that proves the stated user outcome.
