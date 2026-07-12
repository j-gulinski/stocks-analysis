# Pivot roadmap

This is the only live delivery document. It records outcomes and gates, not
session logs or a catalogue of every historical task. Git and `CHANGELOG.md`
retain completed detail.

## Current state

P0 through P3 are complete. Discover and typed-ticker adds create/reuse/reactivate
one visible case and one unclaimed initial job. A claimed worker now produces
an immutable, source-bound `CompanyProfile`/`ResearchSnapshot`; a separate
verifier owns final status, and the fixed company workspace renders that
artifact. Valuation now turns a frozen Research snapshot and explicit human
assumptions into deterministic quarter/F12M/cash-flow/price scenarios; a
separate verifier owns final probabilities and status.

Current delivery focus: **P4 portfolio live gate** — the immutable sync,
deterministic dashboard and verifier-gated review workflow are implemented.
The configured provider reference is not an accepted portfolio name, so the
real holdings pilot and final P4 gate remain open until the exact myfund
portfolio name is supplied.

| Stage | Outcome | Exit gate | Status |
|---|---|---|---|
| P0 · Reset | Four binding docs, obsolete artifacts removed, reads side-effect free, memory non-destructive, worker-only claims | tests prove zero-write reads, proxy verbs, archive preservation, no orphan claim | complete |
| P1 · Research vertical | one `Dodaj do Research` command creates/reuses a company and case and one executable initial job | candidate and ticker paths are idempotent; case appears immediately; one pilot reaches a verifier-labelled snapshot | complete |
| P2 · Tailored research + sieves | common research spine, 2–3 real archetype packs, company overlay, primary-source plan, honest OBS/PA sieves | three comparable factor/coverage views; two representative companies render different relevant sections | complete |
| P3 · Valuation | separate method packs, driver assumptions, deterministic quarter/year and price bridges | one industrial plus one non-industrial pilot reconcile and pass strict verification; sensitivity is labelled | complete |
| P4 · Portfolio | dated myfund/API snapshots, mappings, history, deterministic portfolio analytics and scenario aggregation | repeated sync updates positions; history/benchmark reconcile; portfolio review cites verified company snapshots | in progress · live name blocked |
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

## P1 completion evidence

- Migration `0024` stores immutable, sequential company profiles and research
  snapshots with one artifact per claimed run and one exact verifier record.
- The server derives frozen-input/artifact fingerprints, checks lease ownership,
  job/skill contract, company-bound source versions, fetch-time cutoff,
  chronological history, and exact provenance for every displayed statement.
- Independent verification is persisted before save and owns final status:
  pass/no gaps is verified, pass/any gap is provisional, fail is rejected, and
  needs-human remains blocked.
- ABS AgentRun 21 completed through the real one-shot skill: snapshot/profile/
  verification IDs `1/1/1`, nine cited source versions, eight named gaps,
  provisional status, cleared lease, case monitoring. OPM remained queued.
- 560 backend tests, the frontend production build, PostgreSQL migration/runtime
  checks, skill validation, and browser interaction all pass. Browser QA opened
  ABS from Research, rendered all six sections, and exposed the collapsed source,
  statement-provenance and verifier audit.

## P2 completion evidence

- Discover serves three typed, comparable sieve contracts from the backend.
  `financial_health_br_v1` owns reproducible Altman `>= 8` and Piotroski
  `>= 7` rules over stored market version 31: 384 companies, 366 with both
  inputs, and 45 candidates. OBS and Portal Analiz remain blocked with zero
  candidates and explicit source/factor gaps.
- Seven canonical archetype packs are available through the API, MCP and a
  read-only script. V2 snapshots require one-to-one marker accounting and
  distinguish sourced facts, assumptions, gaps and missing scope; legacy v1
  jobs/ABS reads remain explicit and isolated.
- ABS renders the provisional software/services pack with only 2/5 markers
  addressed. SNT snapshot/profile/verification `2/2/2` renders the materially
  different industrial/consumer pack with three sourced markers and four exact
  marker gaps; all seven pack questions are accounted for without claiming
  missing evidence.
- SNT AgentRun 28 froze and independently reproduced company identity, source
  versions 31 and 39–44, parser/content hashes, failed primary-source attempt,
  deterministic dossier projection, calculation payload and archetype version.
  The strict verifier passed all five checks; final status remains honestly
  `provisional` because nine evidence gaps include a controlled issuer-IR 403.
- 569 backend tests, frontend production build, skill validation, runtime
  invariants and browser QA pass. Browser QA confirms the concise three-sieve
  comparison, Research list state, different ABS/SNT content, v2 audit states,
  exact manifest and verifier evidence.

## P3 design boundary

Codex chooses/explains drivers and probabilities; deterministic services own
financial and price calculations. Preserve an immutable valuation snapshot and
separate strict verification. Backtesting remains a calibration gate, not a
marketing claim.

## P3 completion evidence

- Migration `0025` adds immutable, sequential `ValuationSnapshot` artifacts
  bound to one Research snapshot, claimed run and exact `VerificationRun`.
  Preview and reads are zero-write; queue inputs freeze the Research/source/
  fact/company/price identities, method/template/engine versions, typed
  assumptions, deterministic outputs and both fingerprints.
- `valuation-engine-v2` rejects conflicting consumed facts, non-consecutive
  quarters, look-ahead inputs and non-positive/non-finite prices. It treats
  capex as a positive outlay, does not apply C/Z to non-positive EPS, and keeps
  own-history reversion separate until a valid point-in-time series exists.
- Only `malik_obs_v1` is ready. Areczeks and Elendix remain blocked with named
  source gaps. Industrial/consumer and software/services use distinct driver
  framing; no hidden blend or legacy scenario/AI path enters the canonical
  valuation artifact.
- SNT valuation/verification `1/3` binds Research snapshot 2 and excludes the
  256.562 mln PLN discontinued-operation gain. Strict probabilities 40/45/15
  yield a weighted 305.41 PLN versus frozen 384.60 PLN. ABS valuation/
  verification `2/4` binds Research snapshot 1; probabilities 35/45/20 yield
  78.11 PLN versus frozen 87.80 PLN. Both remain honestly `provisional` because
  upstream Research and scalar lineage have named gaps.
- The first independent code audit rejected mixed source-version facts,
  invalid price handling, stale Research/UI binding, hidden event weight,
  concurrent job risk and model-policy drift. The corrected vertical passed a
  fresh independent approval, 585 backend tests, frontend production build,
  skill validation, runtime/DB invariants and browser QA of list, SNT/ABS,
  optional event preview, Polish gaps and Research-to-Valuation navigation.

## P4 design boundary

Verify myfund's available API/export and terms before expanding ingestion. Sync
is snapshot/upsert with instrument mapping, not append-only de-duplication.
Company analysis stays independent of position size; portfolio aggregation
consumes only verified company scenarios.

## P4 implementation evidence

- Migration `0026` replaces the empty append/skip position ledger with dated
  portfolios, every sync attempt, correctable instrument mappings, immutable
  holdings/value points and verifier-gated portfolio review snapshots.
- Stored reads never fetch. Explicit myfund sync uses the official API key and
  exact portfolio-name contract, sanitizes failures, reuses identical content
  and versions changed content without dropping unknown rows.
- The Portfolio screen makes positions dominant and progressively exposes
  value/cost/P&L/cash, concentration, provider-labelled history and benchmark,
  provisional liquidity and verified-only aligned scenario sensitivity.
- Unreconciled provider totals fail all derived analytics and review closed.
  Malformed history is labelled partial, liquidity excludes price rows learned
  after the snapshot, and frozen risk context names stale Research, current-
  only falsifier timing and sector/archetype co-exposure limitations.
- `stock-portfolio-review` freezes provider, snapshot, mapping, analytics,
  method and eligible valuation identities. Terra-high interpretation and a
  separate Sol-high verifier save one immutable Polish review. Mapping or
  fingerprint drift fails closed; known transaction-instruction forms are
  screened deterministically and the verifier owns the broader no-advice gate.
- Fixture contracts prove zero-write reads, durable failed sync, repeated
  sync/reversion behavior, mapping correction, point-in-time scenario math and
  exact review verification/save retry and strict model roles. The production
  build, 606 backend tests, PostgreSQL migration `0026`, three skill validators
  and browser interaction pass. The live page remains zero-write until its
  explicit sync button is used and then preserves the sanitized failed attempt.
- The real API currently returns “portfolio not found” for the configured
  reference. No holdings were fabricated and no login/password scraping was
  added. P4 closes only after an exact-name sync, repeated changed snapshot,
  reconciled live history/benchmark and one real verifier-gated review.

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
