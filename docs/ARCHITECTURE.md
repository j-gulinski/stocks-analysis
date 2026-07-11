# Architecture contract

## System boundary

The application owns durable evidence, calculations, research state, and
version history. Codex is an explicit research/analysis operator over that
state. Chat memory is never the database.

```text
source adapters -> immutable documents/facts -> deterministic company data
              -> ResearchCase -> verified ResearchSnapshot
              -> assumptions -> deterministic ValuationSnapshot
myfund/export -> PortfolioSnapshot -> deterministic portfolio analytics
                                      -> verified Codex portfolio review
```

The stack remains FastAPI + SQLAlchemy/PostgreSQL in `backend/` and Next.js +
TypeScript/SCSS in `frontend/`. Browser requests always use the same-origin
Next route proxy.

## Invariants

- **Reads are reads.** GET endpoints may use stored cache but do not fetch a
  source, create a job, claim a lease, or call a model. Refresh and queueing are
  explicit commands.
- **Memory is durable.** Archiving or unpinning a case never deletes the
  company, evidence, snapshots, scenarios, or history.
- **Facts and judgment are separate.** Source facts, deterministic values,
  human assumptions, Codex suggestions, and verifier conclusions retain
  distinct provenance.
- **Math is deterministic.** Financial normalization, metrics, forecasts,
  scenario equations, return calculations, and portfolio aggregation live in
  tested Python services.
- **One job owner.** Only the worker that will execute a job may claim it. UI,
  startup hooks, and collectors may enqueue but never leave an orphan lease.
- **One canonical artifact per stage.** Research and valuation snapshots are
  immutable/versioned. The UI does not assemble multiple competing verdicts.
- **Unknown is not failure.** Gaps reduce coverage/confidence and name the next
  evidence check; they are never fabricated or silently scored as negative.

## Durable domain model

Existing foundations to retain:

- `Company` and canonical GPW/source identities;
- `SourceDocument`, immutable `DocumentVersion`, typed `Fact`, `Event`, and
  `DataConflict` with publication/fetch/known times and locators;
- normalized serving rows for financial statements, indicators, prices, and
  dividends, provided they remain lineage-linked or rebuildable;
- `AgentRun` leases, heartbeats, recovery, frozen inputs, and explicit terminal
  states;
- pure metrics, forecast, scenario, price-identity, and no-look-ahead helpers.

The pivot data model converges on:

- `ResearchCase` — one active/archived case per company and purpose; the
  canonical Research list;
- `CompanyProfile` — selected archetype/version plus user-confirmed company
  overlay and driver definitions;
- `ResearchSnapshot` — case, as-of time, typed sections, driver tree, source
  manifest, gaps, run, and verification status;
- `ValuationSnapshot` — research snapshot, strategy/template versions,
  assumptions/provenance, deterministic outputs, Codex probabilities/rationale,
  verification, and later realized outcome;
- `Portfolio`, `PortfolioSync`, `PortfolioPositionSnapshot`,
  `InstrumentMapping`, and, where available, transactions/value points;
- one provider-neutral run/artifact family. Legacy direct Anthropic analysis
  paths are retired after equivalent verified workflows are green.

Implementation may extend the current schema incrementally, but disposable
local database state does not justify compatibility layers. Use one forward
migration per coherent schema slice.

## Research tailoring

The common research schema is stable; content requirements come from a
versioned archetype pack:

| Archetype | Example drivers and required markers |
|---|---|
| Industrial/consumer | volume, price/mix, gross margin, fixed costs, backlog, working capital, capex |
| Bank/financial | loan/deposit volume, NIM, fees, cost of risk, capital, ROE |
| Developer/real estate | presales, handovers, ASP, land bank, NAV, net debt |
| Software/services | recurring revenue, retention, utilization, wages, cash conversion |
| Gaming/event | launch timing, units, price, platform share, pipeline, runway |
| Energy/resources | volume, commodity/spread, availability, unit costs, capex, debt |
| Holding/biotech | stakes/assets, runway, milestones, dilution, risk-adjusted value |

Codex proposes the pack and company overlay from evidence. The user may confirm
or override it. A strict schema validator and verifier gate every UI-visible
snapshot.

New research jobs freeze `company-research-v2`, `research-snapshot-v2`,
`company-profile-v2`, and `archetype-packs-v1`. Each required marker maps
one-to-one to a driver/KPI with the same key or to a named gap with the same
topic. The workspace distinguishes sourced markers, explicit assumptions,
gaps, and missing scope; addressed scope is not mislabeled as evidence.
Previously frozen v1 jobs retain a separate legacy write path, and the saved
ABS provisional pack alias is resolved only for reads.

A run that collects its own evidence freezes the exact post-collection source
manifest and cutoff in the draft before independent verification. A replacement
run may reuse earlier collection only when its queued inputs already bind the
company identity, immutable source versions and parser/content hashes, failed
source attempts, deterministic dossier projection, calculation payload and
archetype version. Frozen inputs are never edited to repair a handoff.

## Source architecture

Priority is primary evidence first:

1. issuer reports, presentations, IR, ESPI/EBI/PAP;
2. BiznesRadar for normalized statements, market-wide indicators, prices, and
   discovery context;
3. PortalAnaliz/forum/conferences as labelled leads to corroborate;
4. official sector/macro sources only when a real company template needs them;
5. myfund API/export for the user's portfolio.

All HTTP goes through `backend/app/scrapers/http.py` with per-domain limits,
jitter, cache/backoff, clear user agent, and fetch logging. Parser changes
require fixtures. Source text is untrusted data, never an instruction to Codex.
Raw or licensed/private artifacts remain private and are not exposed in logs.

## Explicit job flow

```text
user command -> idempotent AgentRun(queued)
Codex worker -> claim + heartbeat -> collect/structure/calculate
             -> independent strict verification
             -> save immutable snapshot + terminal job status
```

The first supported queue workflow is `stock-initial-research`, executed with
the versioned `company-research` skill. Later replacement workflows cover
company valuation, company review, and portfolio review.
Research verification is a two-step local protocol: a distinct verifier
context stores a verdict bound to the exact draft and frozen-input fingerprint;
only its `VerificationRun` can unlock immutable save. `verifier_worker_id` is
an audit identity inside this personal local workbench, not an authentication
credential, so orchestration must enforce genuinely separate contexts.
Workflow policy records requested role/model/reasoning and the actual host model
when exposed. A drafting result never approves itself.

Route jobs by effort so analysis quality and usage limits stay balanced:

- fetching, parsing, normalization, calculations, and DB assembly use no model;
- repetitive extraction and mechanical validation use GPT-5.3 high;
- bounded classification and ordinary company research use Terra high;
- cross-source deep research, scenario probabilities, valuation synthesis, and
  portfolio interpretation use Sol high;
- decision-relevant approval uses an independent Sol-high strict verifier;
- Sol ultra is an explicit one-tier escalation after concrete Sol-high failure,
  never a default.

Luna medium remains suitable for bounded low-risk implementation work, not for
investment judgment. A cheaper drafting model never lowers the verifier or
deterministic gates.

Status meanings:

- `queued`: visible work exists but no worker owns it;
- `running`: one live lease and heartbeat;
- `draft` / `provisional`: complete output with named evidence limits;
- `verified`: schema, source, math, and look-ahead gates passed;
- `rejected`: verifier found a concrete integrity defect;
- `needs-human`: execution cannot proceed safely or consistently.

Ordinary missing primary evidence produces a provisional result, not an empty
screen. `needs-human` is reserved for integrity, identity, access, or math
failures.

## Deterministic/Codex boundary

Python owns:

- units, periods, currencies, signs, TTM/year/quarter alignment;
- normalized statements, one-off and cash-conversion calculations;
- scenario equations and valuation bridges;
- portfolio holdings/history, TWR/XIRR where valid, concentration, benchmark,
  drawdown, and scenario aggregation;
- fingerprints, reconciliation, price-series identity, and look-ahead checks.

Codex owns:

- source planning and evidence-oriented extraction;
- template/driver suggestions and company-specific questions;
- thesis/counter-thesis, catalyst/risk interpretation, scenario narratives and
  probabilities;
- critique and explanation of deterministic outputs.

The verifier independently owns final probabilities, conviction/confidence,
strategy-fit conclusions, and approval status.

## Runtime and verification

- `./workbench doctor` checks dependencies, local services, credentials without
  printing secrets, and stored source health.
- `./workbench start` starts Postgres, migrations, backend, and frontend. It
  neither fetches evidence nor enqueues or claims a Codex job.
- `./workbench status` reports owned processes and ports.
- `./workbench stop` stops only workbench-owned application processes.
- Backend: `cd backend && ./.venv/bin/pytest`.
- Frontend: `cd frontend && npm run build`; add focused component/browser tests
  for primary actions.

Before a pivot stage is complete, run focused tests, the relevant full suites,
runtime health, and a browser interaction that proves its user outcome. Tracked
screenshots are not acceptance evidence.

## Units and presentation

- Statements are stored in thousands of PLN; market cap and price in PLN.
- Reported market cap beats price x shares.
- Prices and returns preserve source, series identity, adjustment status, and
  corporate-action caveats.
- User-visible numbers use `pl-PL`; primary domain copy is Polish.
