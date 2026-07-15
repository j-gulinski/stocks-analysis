# Architecture contract

Defers to `docs/VISION.md` (invariants V1–V10).

## System boundary

The application owns durable evidence, calculations, research state, and
version history. Codex is an explicit research/analysis operator over that
state. Chat memory is never the database.

```text
source adapters -> immutable documents/facts -> deterministic company data
              -> ResearchCase -> verifier-gated ResearchSnapshot
              -> assumptions -> deterministic ValuationSnapshot
myfund/export -> PortfolioSnapshot -> deterministic portfolio analytics
                                      -> verifier-gated Codex portfolio review
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
- **One job owner.** Only the worker that will execute a job may claim it.
  Passive UI renders, startup hooks, and reads never enqueue or claim. Jobs
  are produced by (a) explicit UI/API/CLI commands and (b) the declared
  automatic producers — portfolio-sync coverage, staleness/falsifier
  monitors, and outcome scoring (V7, V8). Automatic producers are
  idempotent, logged, and enumerated in `skills/workbench-actions/SKILL.md`;
  nothing else enqueues.
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
- `MarketFactorSnapshot` — versioned market-wide factor rows parsed from the
  immutable BiznesRadar market pages (rating, multiples, profitability,
  debt, dynamics) that feed the one sieve;
- `ValuationSnapshot` — research snapshot, engine/template versions,
  assumptions with fact bindings, deterministic outputs, drafted
  probabilities with rationale, structural-gate results, verification, and
  later realized outcome (V8);
- `Portfolio`, `PortfolioSync`, `PortfolioPositionSnapshot`,
  `InstrumentMapping`, `PortfolioOperation` (imported transactions/flows),
  and value points;
- one provider-neutral run/artifact family. Legacy direct-provider dossier
  paths, method-perspective artifacts, fields, adapters and rows are deleted
  (V2, V10); there is no compatibility read mode or retained legacy data.

During the active recovery implementation, keep at most one temporary forward
migration for coherent schema work. When its canonical models and code are
finished, delete the entire historical Alembic revision chain and generate one
clean baseline migration. Then drop and recreate the disposable local database,
migrate empty → head and rebuild only canonical data. Never write compatibility
or data-backfill migrations for stale local versions. Later slices may add one
forward migration per new coherent schema outcome until the next explicitly
authorized clean-baseline checkpoint.

## Portfolio boundary

The supported myfund integration is the documented read-only API using one
environment-held API key and the exact configured portfolio name. The app
never stores a myfund login/password and never automates the signed-in web UI.
Opening Portfolio is a zero-write stored-data read; only the explicit sync
command may contact the provider.

Every provider attempt is durable and sanitized. A successful response is
normalized into one immutable `PortfolioSnapshot`, retained position rows and
provider-labelled value/return history. Identical current content reuses the
latest snapshot; changed or later-reverted content receives the next version.
Unknown instruments stay in reconciliation. `InstrumentMapping` is the
explicit correctable identity layer over immutable provider rows; a queued
review freezes the exact mapping states it consumed.
Mappings use a genuine provider-native row key when myfund supplies one;
0-based sequential object keys are disposable collection positions and, like
list payloads, use a stable canonical instrument/account identity rather than
a display ticker or position. GPW equity mapping resolves in order: terminal
`(CODE)` marker → exact/normalized name match against known companies →
persisted manual override (`InstrumentMapping` correction). Ambiguous
matches stay unmapped and visible rather than guessed. Synchronization may
create a minimal GPW `Company` identity for a confidently matched holding
(this feeds auto-coverage); ambiguity always defers to a manual correction.
Cash is exact only for a small provider asset-type contract, including
`Konta gotówkowe`, never because a free-text name happens to contain “cash”.

Snapshot cost and profit are sums of complete current position rows. The
flow-aware provider summary profit is not relabelled as open-position profit;
when any current row lacks profit, both snapshot aggregates remain unknown and
the gap is explicit. Provider profit/contribution history retains its exact
provider-labelled meaning.

Python owns portfolio totals, weights, HHI/concentration, provider-history
projection, 20-session liquidity estimates and aligned company-scenario
sensitivity. Provider-reported return and benchmark series keep those labels.
TWR is computed from the provider's daily value and own-contribution series
(`wartoscWCzasie`/`wkladWCzasie`): daily external flows are the first
difference of contribution, each day's return excludes that day's flow, and
the series compounds. XIRR solves the derived dated flow series plus current
value. When imported operations exist they refine per-position cost basis
and flows; the method and its data window are always stated inline. Missing
series days or unexplained contribution jumps are named gaps that degrade
the claim to partial — never silently smoothed.
If retained rows do not reconcile to the provider total within the explicit
tolerance, the dashboard shows a prominent warning naming the difference and
the affected figures, and analytics that depend on complete rows label
themselves accordingly — analytics never black out wholesale (V7).
Historical liquidity requires each price row to have been scraped by the
portfolio snapshot cutoff.

**Auto-coverage (V7).** Completing a sync triggers the coverage producer:
for every mapped GPW holding it ensures an active `ResearchCase` (creating
one marked `origin=portfolio` and queueing initial research when missing)
and queues a valuation when the latest verified research snapshot lacks a
current valuation or the valuation is stale/falsified. Jobs are idempotent
(one queued-or-running per company/workflow), ordered by position weight ×
staleness, and logged on the sync record.

Only a `verified` valuation bound to the latest point-in-time Research snapshot
may enter scenario sensitivity. Cash and uncovered positions remain unchanged.
The negative/base/positive totals are simultaneous sensitivities, not a joint
probability distribution. An explicit `stock-portfolio-review` job freezes the
snapshot, rows, mappings, method labels, deterministic analytics and eligible
valuation fingerprints; a separate strict verifier owns the immutable Polish
review status.
The frozen risk context binds point-in-time Research/Profile identity and
freshness plus explicitly current-only falsifier states. Shared sector or
archetype groups are evidence-labelled co-exposure only, never correlation,
covariance or a joint probability claim.
Review artifacts persist requested role/model/reasoning separately from the
actual host identity and any substitution/escalation explanation; a disclosed
different host without that explanation is rejected.

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

New research jobs freeze `company-research-v3`, `research-snapshot-v3`,
`company-profile-v2`, and `archetype-packs-v1`. Each required marker maps
one-to-one to a driver/KPI with the same key or to a named gap with the same
topic. The workspace distinguishes sourced markers, explicit assumptions,
gaps, and missing scope; addressed scope is not mislabeled as evidence.
The v3 outlook assesses every profile driver for the next quarter and next 12
months, resolves every frozen profile question plus catalyst, company-specific
result visibility and governance, and records exactly one bounded attempt for
issuer primary, regulatory primary, BiznesRadar, PortalAnaliz and other web.
The frozen profile has at least one company-specific source question, and a
review can freeze only a `human-confirmed` or `human-corrected` profile.
Partial/not-found answers and unknown directions bind named top-level gaps;
every supported direction or resolved answer cites at least one retained
document from its declared source search. Each driver horizon declares its own
searched channels. Channel and manifest-role eligibility derive from stored
source type/provider/host identity rather than draft labels; BiznesRadar stays
normalized and PortalAnaliz stays a lead. Lead/context-only evidence cannot
support a conclusion. Legacy v1/v2 write and read paths, adapters and stored
snapshots are deleted at the clean-baseline reset (V10). History begins with
canonical v3 snapshots rebuilt after that reset.

A run that collects its own evidence freezes the exact post-collection source
manifest and cutoff in the draft before independent verification. A replacement
run may reuse earlier collection only when its queued inputs already bind the
company identity, immutable source versions and parser/content hashes, failed
source attempts, deterministic research projection, calculation payload and
archetype version. Frozen inputs are never edited to repair a handoff.

## Discover market snapshot and the one sieve (V1)

An explicit refresh command fetches the declared set of BiznesRadar
market-wide pages (rating, C/Z, operating margin, net-debt/EBITDA, revenue,
net profit and equity) through the standard HTTP layer — using the
authenticated premium session where anonymous content truncates — and stores
each page as an immutable `DocumentVersion`. Parsers project them into
`MarketFactorSnapshot` rows keyed by company and snapshot batch; a batch
records its exact page/version manifest and coverage per factor. A failed or
partial refresh retains its raw/fetch evidence but cannot publish a batch or
replace the latest complete one.

`workbench_sieve_vN` is a pure server-side function over one batch plus its
earlier immutable C/Z rows: layer A hard kills, layer B improvement
requirement, ordering (see `docs/STRATEGY.md`). The API returns the sieve
id/version, batch id, exact page provenance, thresholds, survivors with
per-factor evidence, excluded companies with kill reasons, and coverage gaps.
It preserves the complete survivor count but returns at most 100 rows ordered
by the deterministic five-component potential score defined in Strategy. The
score is emitted only with all five source-backed inputs; its raw values,
percentiles and equal weights remain machine-inspectable.
At batch creation, a material explicit discontinued-result fact invokes the
generic continuing-operation bridge for net-profit growth and trailing C/Z.
The row freezes the reported/normalized pair, threshold, fact IDs and detailed
document versions, and those additional versions participate in batch
idempotence and the handoff fingerprint. An incomplete bridge yields `null` for
the affected component. The evaluator also blocks B4 when current normalized
C/Z would otherwise be compared with raw own-history snapshots.
There is exactly one sieve; alternative strategies are a new version, never a
parallel filter (V1). Reading Discover writes nothing; `Dodaj do Research` is
the only per-row command. Its typed handoff names the batch and sieve version;
the server recomputes membership and freezes its factor evidence/page manifest
(including B4's earlier C/Z batch/document inputs) in the initial Research run
rather than trusting client rank or factors. A rule whose market source cannot
prove its stated period, such as trailing income for A7, is a coverage gap and
does not fire.

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

The supported Research artifact workflows are `stock-initial-research` and
`stock-company-review`, both executed with the versioned `company-research`
skill. Valuation uses `stock-company-valuation` with `company-valuation`.
Method-perspective workflows are deleted (V2).

**Queue draining (V6).** The Codex run-queue skill recovers expired leases,
then loops: claim one job → execute → verify → save → terminalize, until the
queue is empty or a stop condition fires (same job failed twice, three
consecutive failures across jobs, or an integrity `needs-human`). One job is
in flight at a time; each iteration heartbeats its lease. "One session, one
job" semantics are forbidden.
Company review is an explicit, content-idempotent command after an immutable
snapshot exists: it freezes that prior snapshot and the current latest source
versions, then the claimed worker performs a bounded refresh and saves only the
next independently verifier-gated snapshot. The prior snapshot remains readable
while the review waits or runs. Portfolio review remains a separate workflow.
Research verification is a two-step local protocol: a distinct verifier
context stores a verdict bound to the exact draft and frozen-input fingerprint;
only its `VerificationRun` can unlock immutable save. `verifier_worker_id` is
an audit identity inside this personal local workbench, not an authentication
credential, so orchestration must enforce genuinely separate contexts.
Workflow policy records requested role/model/reasoning and the actual host model
when exposed. A drafting result never approves itself.

Valuation preview loads only consumed immutable Facts inside the bound Research
manifest and cutoff. Differing values or units for a consumed `(fact_key,
period)` fail; identical duplicates resolve deterministically to the latest
document version. Shares and market cap resolve from one latest parsed
BiznesRadar profile version known by `as_of`; both immutable Facts must match
the canonical company, expected units and that same document version. Legacy
mutable Company scalars remain a fail-visible provisional fallback only. The
current price must be finite, positive, dated and scraped by `as_of`, preserve
source/series/basis identity, and point to a parsed immutable source version
for the same company. A `raw_unverified` row may serve only as the current
valuation reference when its price × shares reconciles to reported market cap
within 2%; it remains `return_series_eligible=false` and cannot support return,
benchmark or backtest claims. Identity/cutoff conflicts fail closed; missing or
mismatched lineage stays a named gap. One company may have only one queued or
running valuation; snapshot version is assigned at execution and checked again
at verify/save.

The valuation draft freezes the engine and template versions, the retained
Street expectation curve, typed five-year assumptions with semantic fact or
Research-claim bindings, a selected primary method plus independent
cross-checks, an optional conditional probability tree, deterministic outputs
and input/calculation fingerprints. The drafter owns mechanisms, assumptions,
method selection and any judgmental conditional probabilities — all
company-specific (V4). Python owns the arithmetic and derived leaf/scenario
probabilities.

The canonical `valuation-snapshot-v3` / `valuation-engine-v4` contract also
freezes one to four shared company-driver IDs per scenario. Each driver has a
mechanism, runway evidence, capital requirement and five explicit fiscal-period
impact rows. The anchor row reconciles each scenario to the base anchor; later
rows reconcile year-on-year changes in revenue, EBITDA margin, depreciation/
revenue, capex/revenue, delta-NWC/revenue, cash tax and net-financial-result/
revenue. Each valuation driver binds to its matching frozen Research
profile-driver and that driver's factual/calculated Outlook claim; an unrelated
raw fact or another driver's claim cannot underwrite it. Terminal growth is
accepted only with explicit reinvestment and
incremental-ROIC assumptions that satisfy `g = reinvestment × incremental
ROIC`. The deterministic driver-to-value output then computes operating CAGR,
margin change, cumulative reinvestment/FCFF, cash conversion, an exact
current-net-debt → cash after financing/event cash/capital allocation →
target-net-debt bridge (positive allocation is cash outflow; negative is a
financing inflow),
and method-specific current-price hurdles. DCF exposes a present value gap;
only future-period relative prices expose annualized repricing, and dated method
ranges never mix those bases. It is part of the one engine, not a score,
persona or second valuation method.

**Valuation structural gates (computed by the backend before any verifier
opinion; any hit → automatic `rejected` with the reason stored):**

1. exact-draft integrity — saved payload equals the frozen draft;
2. identity and source semantics — price × shares reconciles to market cap;
   each `street_estimate` cites the matching `consensus.<metric>.*` fact; a
   current-price-derived forward trading multiple is forbidden as a target;
3. five-year math recomputation — P&L, recurring/reported bridge, FCFF,
   EV-to-equity bridge, P/E, EV/EBITDA, EV/EBIT, DCF sensitivities and reverse
   DCF reproduce deterministically; all scenarios share periods/fractions/
   timings, a partly elapsed first fiscal year has an
   explicit FCFF fraction and discount exponent rather than a hidden full year;
4. potential-driver reconciliation — the same company driver IDs span bad,
   base and good; driver labels/Research keys remain stable globally; every
   core or event scenario-driver binds to its own frozen Research-driver Outlook
   evidence; five-period revenue, margin, depreciation, capex, NWC, tax and
   financing impacts sum exactly to the anchor/year-on-year forecast path; the
   deterministic bridge preserves those IDs and terminal
   growth reconciles to reinvestment × incremental ROIC;
5. unknown neutrality — absence can lower coverage or disable a method, but
   cannot become zero, an adverse assumption or a probability input;
6. methodology independence — one company-specific primary method plus
   relative/intrinsic cross-check coverage; future EV methods require a
   reconciled target-net-debt rollforward; only same-date calculated methods
   enter dispersion, which fails instead of being hidden by averaging;
7. conditional probability structure — Python derives mutually exclusive and
   exhaustive leaf/scenario probabilities from evidence-bound nodes. Direct
   unexplained percentages, known house defaults and cross-company
   near-duplicates fail. `uncalibrated` carries no percentages or weighted
   value; empirical claims require a frozen dataset fingerprint, cutoff,
   sample, Brier score and reliability bins;
8. rationale and company-specificity — every core assumption binds a
   semantically eligible fact/Research claim or is explicit judgment; the full
   five-year vector must differ from templates and other live companies;
9. scenario completeness — each scenario names mechanism, catalyst or
   counter-driver and a dated falsifier; an event splits recurring P&L from
   one-off P&L/cash, is mutually exclusive, stays out of relative multiples,
   is discounted at its own DCF timing and requires DCF as primary;
10. lineage — fingerprints current, look-ahead boundaries respected,
   drafter ≠ verifier worker.

The strict verifier then judges what cannot be computed — evidence fit,
mechanism plausibility, whether the driver runway and capital burden are
underwriteable, and probability reasonableness — and must return either
concrete findings or per-check justification referencing the evidence
examined (V5). A verdict with empty findings and empty justifications is
itself rejected. Save recomputes every deterministic output, including a
weighted value only when the probability posture supports one, binds the exact
draft fingerprint, creates one `ValuationSnapshot`, terminalizes the run and
clears its lease. Passing output with any named upstream or scalar-lineage gap
is `provisional`.

Route app jobs and development sessions by task shape, using the lowest
reasoning effort that reliably passes the relevant gate. Use exact public model
slugs in queued policy and the Roadmap; `Sol high`-style shorthand is not a
durable model identity. This is the single routing table (the ledger lives in
`docs/model-usage.md`):

| Work shape | Requested Codex model | Reasoning | Typical use |
|---|---|---|---|
| Deterministic | no model | none | fetch, parse, normalize, calculate, query, fingerprints, DB assembly |
| Mechanical coding/check loop | `gpt-5.3-codex-spark` | model default | near-instant text-only test, lint and focused UI/code iteration when the Pro research preview is available; never financial judgment or a queued artifact worker |
| Clear and repeatable | `gpt-5.6-luna` | low | bounded extraction, classification, transformation, fixture shaping and structured summaries with a known good result |
| Everyday implementation | `gpt-5.6-terra` | medium | scoped API/UI wiring, ordinary debugging, scraper fixes, queue plumbing |
| Multi-source company Research | `gpt-5.6-terra` | high | evidence synthesis, driver/outlook drafting, ordinary company review |
| High-value ambiguous work | `gpt-5.6-sol` | high | product/architecture decisions, valuation scenarios and probabilities, complex portfolio or replay synthesis |
| Strict decision verification | `gpt-5.6-sol` | high, independent | adversarial Research, valuation, portfolio and replay approval; never the drafting context |
| Evidence-backed escalation | `gpt-5.6-sol` | xhigh | only after a representative eval or concrete high-effort failure shows that more checking is needed |
| Exceptional single-task escalation | `gpt-5.6-sol` | max | only after a concrete xhigh failure or representative eval shows a material gain |

This mapping follows OpenAI's current Codex guidance: Luna for clear repeatable
work, Terra as the everyday workhorse, Sol for complex/high-value work, and the
lowest reasoning effort that achieves the outcome. `Ultra` is multi-agent
orchestration, not a model or reasoning tier; use it only for genuinely
independent workstreams when the user or applicable agent/skill instruction
requests delegation. Sources: [Codex model selection](https://learn.chatgpt.com/docs/models),
[Codex speed and Spark](https://learn.chatgpt.com/docs/agent-configuration/speed),
[GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model).

Record requested model and effort separately from `actual_host_model`. If the
surface cannot select or expose the requested deployment, record
`host deployment not exposed` plus the substitution; never imply that a
requested model actually ran. A drafter and verifier must remain distinct
contexts even if both legitimately use Sol.

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
- thesis/counter-thesis, catalyst/risk interpretation, scenario narratives,
  assumptions and probabilities — always company-specific and
  evidence-bound (V4);
- critique and explanation of deterministic outputs.

The backend owns the structural gates. The strict verifier owns judgment
review and final approval status; it never rewrites the draft (V5).

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
- Drift gate: `backend/tests/test_vision_contract.py` encodes VISION
  invariants (single sieve, no author branding, no seed constants, no house
  probability defaults, adversarial verifier contract, queue-drain
  semantics, phase-aware research list). It runs with the backend suite and
  must never be weakened to pass.

Before a pivot stage is complete, run focused tests, the relevant full suites,
runtime health, and a browser interaction that proves its user outcome. Tracked
screenshots are not acceptance evidence.

## Units and presentation

- Statements are stored in thousands of PLN; market cap and price in PLN.
- Reported market cap beats price x shares.
- Prices and returns preserve source, series identity, adjustment status, and
  corporate-action caveats.
- User-visible numbers use `pl-PL`; primary domain copy is Polish.
