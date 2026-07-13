# Delivery roadmap

This is the only live delivery document. It contains active outcomes,
dependencies, blockers, and acceptance gates. `CHANGELOG.md` and Git preserve
completed implementation evidence.

## North-star outcome

Make the existing `Discover -> Research -> Valuation -> Portfolio` product the
investor's default GPW analysis workspace: trustworthy enough to find what
deserves attention, deep enough to build durable company understanding, clear
about how separate Polish-market investor methods view the evidence, and
practical enough to connect verified scenarios with the real portfolio.

This is an incremental completion of the current product. It does not replace
the FastAPI/Next.js stack, durable evidence model, `ResearchCase`, immutable
snapshots, deterministic engines, explicit job queue, or strict-verifier
boundary.

## Current state

- P0-P3 delivered reusable foundations: zero-write reads, explicit commands,
  immutable source lineage, one canonical Research case, tailored archetype
  packs, verifier-gated Research snapshots, and deterministic valuation.
- Discover currently works only as a financial-health shortlist. Its live
  snapshot contains 384 GPW companies, 366 with joint Altman/Piotroski coverage,
  and 45 candidates. Its immutable source lineage, universe-continuity and
  stale-factor gates are implemented. OBS and Portal Analiz have no market-wide
  candidate data; their union/overlap contract is now rendered honestly, but
  live multi-sieve coverage remains blocked on source facts.
- All eight mapped holdings have strict-verifier-passed Research, but ordinary
  evidence gaps keep every current artifact provisional. Company profiles can
  now be confirmed or corrected into immutable human-owned versions; an
  explicit review must still consume the selected version before it changes a
  canonical snapshot.
- The valuation and portfolio engines are implemented. No holding yet has an
  eligible verified valuation bound to its latest Research snapshot, so real
  portfolio scenario coverage remains 0%.
- Malik/OBS has a source-grounded Codex lens, the only ready Valuation pack and
  the first supported snapshot-bound Research perspective; its market-wide
  Discover sieve remains planned. The Research catalog freezes its source
  limits, and an explicit command can create one separate verifier-gated Malik
  perspective over a canonical snapshot. Areczeks remains source-blocked;
  Elendix exposes two retained dated fragments as partial provenance but remains
  draft until a complete, independently reviewed corpus exists.
  No expert method has point-in-time performance calibration.

The active engineering slice is **R1 · user-owned Research memory**. **V1 ·
Verified scenario coverage** remains active in parallel where current evidence,
scalar lineage, and explicit user assumptions are available.

## Active outcomes

| Order | Outcome | Exit gate | Status |
|---|---|---|---|
| D1 | trustworthy Discover integrity and context | complete-universe and freshness gates, decision context, correct add/reactivate behavior | in progress · integrity/freshness/provenance implemented; final user-flow gate remains |
| D2 | comparable sourced sieves and overlap | three per-sieve candidate views share one contract and controlled overlap renders correctly | in progress · union contract/renderer ready; OBS/PA market-wide facts blocked |
| R1 | user-owned Research memory | confirmed/corrected profile produces a new version and review without rewriting history | in progress · immutable human profile/review-freeze contract and editor ready; real browser mutation and verifier-save gate await a user-confirmed company change |
| M1 | named method catalog and Codex perspectives | supported packs render separately over one evidence snapshot; synthesis preserves disagreement | in progress · source-frozen catalog and first verifier-gated Malik/OBS perspective artifact/rendering are implemented; partial Elendix provenance is visible but a second supported corpus and synthesis remain pending |
| V1 / P4 | verified valuation and portfolio scenario coverage | real portfolio review consumes at least two eligible verified scenarios | in progress · evidence/user-input dependent |
| W1 | daily `Do sprawdzenia` workspace | stored read-only agenda leads to explicit bounded actions across the four stages | after D1, R1, and first V1 coverage |
| P5 | point-in-time calibration | reproducible benchmark-relative replay and disclosed calibration limits | waits for historical data |

## D1 · Discover integrity and context

Build on the stored BiznesRadar snapshot and current explicit refresh command.
Do not add a crawler or model call to Discover reads.

- Fail closed when the market page is truncated, structurally incomplete, or
  implausibly discontinuous from the last good universe.
- Separate content version time, last successful source check, factor/report
  period, and latest failed refresh. Stale factors remain visible and cannot
  rank as current without an explicit stale state or policy.
- Return and render source/version, membership factors, factor gaps, missing
  strategy questions, WIG bucket where sourced, sector, and size as neutral
  context.
- Freeze Discover-origin provenance: sieve ID/version, membership factors,
  source/parser identity, and as-of time. Typed-ticker entry remains available.
- Fix closed-case reactivation and keep Discover usable when the Research list
  read fails independently.
- Keep the stored-company data-readiness tool explicitly separate from Discover
  and investment potential. It evaluates the full eligible stored-company set
  before applying its output limit.

Gate: parser fixtures reject truncated universes; stale-company fixtures show
the explicit state; repeated GETs remain zero-write; the production build and a
browser flow prove context, source freshness, one-click add, duplicate reuse,
and closed-case reactivation.

## D2 · Comparable sourced sieves and overlap

- Evolve the typed sieve response so each candidate carries per-sieve
  membership, factors, coverage, source/freshness, and overlap; do not hard-code
  the financial-health list in the UI.
- Populate `obs_operating_improvement_v1` only from a bounded, versioned
  market-wide snapshot of its declared factors. Catalyst and priced-in judgment
  remain Research gaps when not available deterministically.
- Populate `pa_value_catalyst_v1` only after retained Areczeks/Elendix method
  sources and bounded market-wide inputs exist. Attribute each factor to the
  author source, standard finance, or Workbench operationalization.
- Compare columns and overlap rather than producing a universal expert rank.

Gate: one frozen fixture contains companies unique to each sieve, overlapping
two, overlapping all three, and missing factors. API and browser tests prove
distinct lists, visible overlap, equal source/coverage contracts, and honest
blocked states. D2 closes the multi-sieve Product acceptance gap.

## R1 · User-owned Research memory

- Let the user confirm or override the proposed archetype, segments, drivers,
  KPIs, competitors, source questions, and unusual risks.
- Store every correction as the next immutable `CompanyProfile` version with
  author/time/reason; never rewrite evidence or an earlier profile/snapshot.
- An explicit review job freezes and consumes the confirmed profile. Model
  proposals and human corrections retain distinct provenance.
- Lead the company page with what changed, current understanding, strongest
  evidence, main uncertainty, and one next useful action.

Gate: a browser flow changes a proposed driver or archetype, queues one
idempotent review, produces a new verifier-gated snapshot, and shows the prior
profile and snapshot unchanged in History.

## M1 · Named method catalog and Codex perspectives

- Introduce the stage-aware method manifest defined in `docs/STRATEGY.md` using
  the existing versioned skill/template foundations; do not create a parallel
  company-truth artifact family.
- Keep Malik/OBS supported only for the stages its evidence and inputs justify.
  Retain, cite, and independently review one additional Polish-market method
  corpus before promoting its Research perspective; add later methods one at a
  time by the same gate.
- Map every applicable supported method over the same frozen Research evidence
  as `supports`, `contradicts`, `unknown`, or `not applicable`, with source
  coverage, blind spots, falsifiers, and next checks.
- Codex synthesizes agreement and disagreement in Polish. It does not simulate
  an expert voice, average shared facts into consensus, or reuse legacy
  conviction/alignment scores as the canonical verdict.
- A second Valuation method becomes available only after retained sources, a
  deterministic compatible template, two contrasting pilots, and an
  independent strict pass.

Gate: two unlike companies render materially different method perspectives;
every enabled pack freezes its manifest/source versions; unsupported packs show
named gaps; the verifier proves attribution, non-impersonation, applicability,
unknown handling, and no hidden blend.

## V1 / P4 · Verified scenario coverage

Close the real decision path before broadening company collection further.

- Complete one industrial and one non-industrial company from current primary
  evidence through latest Research, scalar lineage, explicit human assumptions,
  deterministic valuation, independent verification, and portfolio consumption.
- Expand after those pilots by portfolio weight, staleness, and decision need,
  one bounded company at a time. Never fabricate an assumption to increase
  coverage.
- Keep provider reconciliation, method identity, Research binding, and
  simultaneous-sensitivity labels fail-closed.

Gate: a real portfolio review consumes at least two eligible verified company
scenarios and reports non-zero value coverage. Every remaining material holding
is covered or shows a named evidence, scalar-lineage, or user-input dependency.

## W1 · Daily `Do sprawdzenia` workspace

Add a concise agenda to the Research landing rather than a fifth navigation
stage or generic dashboard.

- From stored state, show material source changes, stale cases, unresolved
  conflicts, testable falsifiers, important gaps, valuations awaiting user
  assumptions, and portfolio positions lacking current verified coverage.
- Give each item one clear next action into the existing Discover, Research,
  Valuation, or Portfolio flow.
- Opening the agenda is a zero-write read. Source refresh, quick/deep Codex
  review, and verification remain separate, explicit, bounded commands.

Gate: deterministic freshness and delta tests pass; every displayed change has
a source or explicit unknown; browser QA proves a morning session from agenda
to one durable outcome without hidden refresh, queue claim, or model call.

## P5 · Calibration and learning

Preserve every investor method separately while adding point-in-time universe
history, official corporate-action-aware total returns, delistings/failures,
mixed cases, untouched holdout, and 3/6/12/24-month outcome windows.

Gate: replay is reproducible and no-look-ahead; results are benchmark-relative
and report direction/range accuracy, falsifier timing, Brier/calibration
measures, costs, latency, and limitations. Until then, no performance claim or
calibrated method weighting is allowed.

## External and user-input dependencies

- OBS Discover needs a bounded market-wide factor snapshot.
- Areczeks needs dated method sources with exact attribution; Elendix needs a
  fuller dated corpus and independent review beyond its two retained fragments.
- Verified valuations need current primary evidence, scalar lineage, and the
  user's explicit scenario assumptions.
- P5 needs official point-in-time universe and corporate-action-aware return
  data.

## Default-workspace gate

A real company must be discoverable with an explainable source/freshness trail,
addable or reactivatable in one action, correctable by the user, interpretable
through separate source-backed method lenses, valuatable through verified
scenarios, visible in portfolio exposure, and returnable from the read-only
daily agenda. Source, time, assumptions, method versions, verifier decisions,
and prior artifacts remain inspectable at every step.

Every active slice finishes with focused contracts, the relevant full backend
suite, the frontend production build, runtime health, and one browser interaction
that proves its user outcome.
