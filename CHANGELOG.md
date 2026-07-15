# Changelog

Release-level changes and durable decisions only. Granular history before the
product reset remains available in Git at and before `2ac75d0`.

## 2026-07-15 · Evidence-bound potential bridge

- Reviewed an authenticated eight-thread user-nominated PortalAnaliz cohort,
  prioritizing self-reported returns above relevant market benchmarks while
  retaining virtual-portfolio, absolute-only and underperformance caveats.
  Only recurring author-neutral valuation mechanics were retained. The durable
  finding is that potential must be an operating driver with a measurable
  runway, capital burden and price-implied hurdle; concentration, trade timing,
  cash buffers and staged selling remain outside the engine.
- Advanced the sole canonical workflow to `company-valuation-v4`,
  `valuation-snapshot-v3`, `valuation-engine-v4`, `valuation-templates-v3` and
  `valuation-gates-v3`. Every core scenario now carries the same named company
  drivers, whose five-period revenue, EBITDA-margin, depreciation, capex,
  working-capital, tax and financing impacts must exactly reconcile the
  anchor/year-on-year forecast. No compatibility
  reader or parallel valuation path remains.
- Added terminal growth discipline (`g = reinvestment × incremental ROIC`) and
  deterministic potential diagnostics: driver runway, operating CAGR, margin
  change, cumulative capex/NWC/FCFF, target-net-debt/capital-allocation
  rollforward and method-specific current-price hurdles. DCF shows a present
  value gap; only future-period relative prices show annualized repricing, and
  event cash is discounted at its own timing. The UI renders the
  evidence→driver→result→value bridge ahead of scenario cards and states what
  reverse DCF holds constant.
- Extended strict verification with a separate potential-underwrite judgment
  and a computed structural gate that records driver evidence coverage, exact
  reconciliation residual and output identity. The backend suite and production
  frontend build pass (361 backend tests); the independent review found and
  closed Research-driver key/label lineage bypasses. The live honest-empty flow
  is healthy, while a renewed cost-bearing valuation artifact and representative
  company browser acceptance still require Kuba's explicit authorization.

## 2026-07-15 · SNT expectation-led valuation recovery

- Tightened the V4 structural gate to compare every five-year economic input,
  optional-method availability and a non-recurring event payload. A changed
  cash-tax, depreciation, financing or event assumption can no longer evade
  company-specificity checks or falsely reject a valid event scenario.
- Regenerated the clean baseline after deleting the remaining retired artifact,
  raw-forum, watchlist and monitor schema paths. The disposable PostgreSQL
  database was recreated from empty; migration parity, a fresh Discover batch
  and a fresh myfund Portfolio snapshot pass. Canonical Research/Valuation are
  deliberately not recreated until Kuba renews authorization for that
  cost-bearing queue work.
- Made retained BiznesRadar analyst expectations a visible baseline in
  Discover and Valuation, including fiscal-year revenue/EBITDA/EBIT/net-income
  levels, growth, ranges, forecast counts and dispersion. Missing consensus is
  neutral and never reduces a candidate's score.
- Repaired Discover's treatment of material discontinued results. Immutable
  batch v6 now freezes a detailed continuing-operation bridge and uses it for
  earnings growth and trailing C/Z, or leaves the component neutral when the
  bridge is incomplete. SNT therefore uses +80.62% and 21.77x instead of the
  Syn2Bio-distorted +1,953.65% and 5.97x, with the raw values and exact lineage
  visible; it no longer compares normalized current C/Z with raw history.
- Replaced the failed one-period SNT valuation logic with
  `valuation-engine-v3`: a five-period operating/FCFF path with explicit stub
  timing, recurring-result normalization, independent P/E and EV/EBITDA
  cross-checks, DCF sensitivity, method-dispersion gates and reverse
  expectations. BiznesRadar forward P/E is classified as a current-price
  identity, never a target multiple. Uncalibrated scenarios publish no
  probabilities or weighted value.
- Completed adversarial fail/repair/pass cycles for both SNT Research and
  Valuation. The live UI now exposes the Street variance bridge, five-year
  paths, valuation anchors, reverse DCF and sensitivity; the obsolete
  engine-v2 SNT snapshot/run was deleted. Full backend tests, production build
  and browser acceptance pass; the remaining WACC component-source gap stays
  visible and non-directional, while the pre-demerger multiple comparability
  caveat is shown adjacent to the affected methods.
- A final independent cross-stage audit recomputed the continuing-profit
  bridge, batch admission fingerprint and valuation fingerprints, verified the
  null probability/weighted-value posture and canonical-only storage, and
  passed with no open severity-1/2 finding. Fresh Discover batch #2 ranks SNT
  #26 at 63.2 instead of the distorted #5 at 80.7.

## 2026-07-14 · VISION reset phase boundary

- Reopened S2–S3 after the owner rejected the first clean-baseline SNT output:
  the saved Research omitted publicly available issuer evidence about the
  non-cash Syn2bio demerger, retained radiopharma operations, order visibility
  and recurring revenue, while the valuation treated a derived BiznesRadar
  forward trading C/Z as an independent target multiple and exposed unsupported
  32/46/22 probabilities. Valuation now renders each saved probability rationale
  beside its percentage. The issuer adapter can freeze one explicitly
  authorized exact same-host PDF URL before using the unchanged bounded detail
  fetch; this does not promote an authorization link to report evidence. Fixed
  the shared polite fetcher so a new Requests session replaces its built-in
  `python-requests` user-agent with the configured browser user-agent. The SNT
  index plus H1, ESPI 23, ESPI 28 and ESPI 36 are now retained canonically; no
  replacement artifact is created before the owner confirms the exact company
  profile required by V4.
- Closed the fresh-artifact S2–S5 gate with canonical SNT snapshots after the
  clean-baseline reset. Research v3 has 11 explicit evidence/coverage gaps and
  one strict-verifier minor finding on duplicate gross-margin facts. Valuation
  v2 normalizes the 2026Q2 discontinued-result uplift, keeps gross margin as a
  visible judgment, retains raw-price/market-cap mismatch, and is therefore
  provisional. Both jobs terminalized through their independent verifier gates;
  the queue is empty. Browser acceptance confirms the real SNT artifact across
  Discover, Research list/company, Valuation and Portfolio, with Portfolio
  correctly excluding a provisional valuation from scenario aggregation.
- Completed the S2–S5 mechanical recovery boundary: current Research reads now
  require a v3 snapshot, v2 profile and complete V5 verifier evidence; current
  Valuation reads require a v2 artifact bound to that Research. Direct stale
  IDs are rejected rather than projected into compatibility output. The company
  view leads with Valuation/Brief and keeps profile, evidence and details
  independently collapsed; a saved scenario result precedes editable inputs.
- Replaced all 32 historical Alembic revisions with generated
  `0001_canonical_clean_baseline`, removed retired Research/valuation tables
  and promotion/author fields from the ORM, and recreated the disposable local
  PostgreSQL database from empty. Alembic/ORM parity, the full backend suite
  and the frontend production build pass. A fresh Discover batch and myfund
  Portfolio snapshot have been rebuilt; no canonical Research or Valuation
  artifact is created until the user selects a company and authorizes queue
  execution.
- Reopened Research + Valuation as one recovery slice after live acceptance
  showed legacy v1 valuations, author-labelled judgment, repeated probability
  mixes and metadata-led layouts still reaching the current UI. The Roadmap is
  now the only execution plan: canonical read boundaries and the short
  valuation-first reading path precede a disposable-data reset and queue
  rebuild; Portfolio resumes only after that gate passes.
- Replaced ambiguous model-tier prose with one exact routing contract and
  executable queue policy: deterministic work uses no model, mechanical coding
  loops may use the `gpt-5.3-codex-spark` preview, clear repeatable work
  requests `gpt-5.6-luna` low, everyday work requests
  `gpt-5.6-terra` at the lowest sufficient effort, and ambiguous/high-value
  work requests `gpt-5.6-sol`. Requested and actual host identity are recorded
  separately; Ultra is orchestration, never a model tier.
- Added a browser-first Vision acceptance skill and made it mandatory after
  implementation sessions. Focused deterministic tests retain contract/math
  coverage, while the running Discover → Research → Valuation → Portfolio flow
  is the acceptance artifact; raw unit-test count is no longer treated as
  product proof.
- Made the S2–S5 recovery explicitly destructive under V10: finish canonical
  code first, delete all legacy readers/adapters/schema fields, replace the 32
  historical Alembic revisions with one generated baseline, then drop/recreate
  the disposable local database and refetch/rebuild only canonical artifacts.
  Normal startup remains non-destructive.
- Made V1–V10 binding through `docs/VISION.md` and an executable drift gate.
  Discover now exposes one honestly blocked Workbench sieve until its complete
  market-factor batch exists; Research is phase-aware and accepts only v3
  writes; Valuation has one company-specific engine with computed structural
  gates and adversarial verification.
- Deleted callable compatibility paths for alternate sieves, author-labelled
  methods, generic analysis completion, pre-session/quick/deep/scout/backtest
  workflows, legacy Research/forecast/assumption APIs, and their dead UI.
- Queue operation now exposes only the four canonical artifact workflows and
  the run skill drains eligible jobs with lease recovery and bounded failure
  caps. Portfolio reconciliation warns and degrades affected figures instead
  of hiding all analytics.
- Added immutable price-source lineage plus forward schema foundations for the
  expanded market-factor batch and portfolio operations, then aligned six
  historical PostgreSQL JSON columns with the ORM's JSONB contract in migration
  0032. Further delivery starts with S1; missing factor coverage remains visible
  rather than producing false candidates or false sieve provenance.
- Delivered S1's one exclusion-first Discover outcome: a guarded immutable
  seven-page BiznesRadar batch, source-provenanced `workbench_sieve_v1`,
  inspectable survivor/exclusion evidence, and server-recomputed frozen
  Discover-to-Research handoff. A live 384-company batch exposes 93.2% of its
  declared A1–A5/B1–B3 base coverage; A6, A7 and B5 remain named gaps rather
  than fabricated signals. Browser acceptance renders the source batch,
  per-factor provenance and visible gaps, then expands the survivor list
  without a filter selector. Discover now surfaces at most 100 survivors in
  one deterministic 0–100 potential order: the equal-weight mean of sourced
  revenue, net-profit, margin-change, current-profitability and current-C/Z
  percentiles. Explicit caps prevent low-base outliers from taking extra rank;
  report-period recency/alignment gates keep stale rows out of the percentile
  cohort, and own-history cheapness requires a snapshot at least 30 days old.
  Composite health ratings and leverage remain exclusion gates rather than
  score points. There is no imputation, hidden tie-break factor, or probability
  claim, and the full survivor count remains visible.
- Structural valuation-gate failures now durably override any requested
  verifier verdict to `rejected` with computed reasons. Portfolio keeps partial
  risk, liquidity, scenario and review analytics visible when retained rows do
  not reconcile to the provider total.
- Completed S2's canonical Research flow. The list agenda is now derived from
  stored collection/snapshot/valuation state, newly parsed evidence, staleness
  and fired falsifiers; each detail renders Research → Valuation → History in
  one page. Historical verifier payloads remain readable but are explicitly
  labelled `legacy-incomplete`: their old boolean checks are neither displayed
  nor upgraded into V5 evidence, while all new writes keep the strict
  adversarial contract. The remaining MCP dossier tool, standalone dossier
  script/service and dead frontend dossier client/types were deleted so the
  Research workspace is the only company-analysis read path.

## 2026-07-13 · V1 first live non-industrial valuation checkpoint

- Completed the live ABS valuation against Research snapshot 15 after
  backtracking three scenario grids. The selected grid keeps C/Z fixed at 19.9
  across the downside/base/upside cases so 68.68 / 91.20 / 111.33 PLN reflects
  operating outcomes rather than an unsupported multiple re-rating.
- Independent exact-draft verification retained 30/50/20 probabilities and a
  weighted 88.47 PLN result versus the frozen 87.80 PLN price. Valuation v2 is
  current and inspectable, while v1 remains immutable history.
- The result stays provisional and cannot increase Portfolio coverage: shares
  and market cap are not immutable-fact-bound, the price series is still
  raw-unverified for corporate actions, and the upstream Research snapshot
  retains eight disclosure gaps. The next V1 slice closes lineage before the
  industrial comparison company is valued.

## 2026-07-13 · R1 self-resolving forward Research

- Added the versioned `company-research-v3` / `research-snapshot-v3` contract.
  Every new full flow must assess each frozen company driver for the next
  quarter and 12 months, answer every profile question, and resolve the
  company-specific catalyst, result visibility and governance from a retained
  five-channel source-completion trail. Unknowns remain named gaps.
- The save gate now rejects missing/duplicate channels, drivers, questions or
  source-manifest rows; unsupported directions; undeclared answer evidence;
  and conclusions backed only by PortalAnaliz/context. Frozen v1/v2 jobs keep
  their original write contracts and render unchanged.
- Review queueing now requires a human-confirmed/corrected profile with at
  least one company-specific question. Stored provider/type/host identity fixes
  channel/role eligibility, every driver horizon declares its searched
  channels, and the renderer labels fact/calculation/assumption provenance.
- Research renders the typed Outlook before Thesis, removes already answered
  questions from generic next checks, and renders a duplicated thesis/top-level
  check only once using the richer row with its suggested source. No profile,
  job, valuation or investment decision is created by a read.
- Extended the bounded issuer adapter to preserve multiple official index
  pages. ABS now retains numbered inline current reports separately from its
  periodic-report index and can ingest the Q1 2026 PDF; the faulty intermediate
  link extractor remains auditable but cannot authorize report downloads.
- Completed the live ABS gate after comparing three profile variants and
  backtracking the stale employment wording: immutable profile v3 and snapshot
  v3 are strict-verifier-passed, the prior versions remain unchanged, and the
  result stays provisional for eight named disclosure gaps. The browser shows
  all five source attempts, including the inaccessible PortalAnaliz subscriber
  lead, without treating unavailable content as evidence.

## 2026-07-13 · D1 integrated Discover gate

- Closed the stored-source browser gate: Discover showed its universe,
  coverage, source version and freshness; one NWG action created one case and
  one initial job; the duplicate action reused both.
- Reactivating the temporarily closed ABS case from Discover preserved case
  identity, its initial run, the canonical snapshot and both snapshot
  fingerprints while appending the explicit lifecycle history.
- Made initial-run lookup reuse an exact case-bound legacy run when it predates
  idempotency keys. Read views and closed-case reactivation no longer lose that
  identity or queue a duplicate initial research job.

## 2026-07-13 · Documentation contract consolidation

- Made Architecture the single invariant and model-routing rulebook, reduced
  AGENTS/README to operating pointers, and limited full Roadmap prose to the
  next D1 slice plus the open R1 and V1/P4 user/evidence gates.
- Corrected the live method-readiness contract: Malik/OBS Research perspectives
  are supported and verifier-gated, while saved Research artifacts remain
  honestly provisional when evidence gaps survive verification.
- Added the supplemental method-perspective workflow to Architecture and the
  one-job queue operator, and made D1's browser mutation flow the single next
  engineering gate; R1 and V1/P4 remain explicit user/evidence waits.
- Rotated the model-use ledger to recent decisions and excluded local review
  captures from Git because they may contain personal portfolio or Research
  state and are not acceptance evidence.

## 2026-07-13 · D2 Discover filter and ranked-list layout

- Replaced the three-card layout with an inline sieve selector and one active,
  locally ordered candidate list. Unavailable sieves remain visible but cannot
  be selected until their declared source coverage exists.
- Each row now shows its local rank, concise ordering basis, and expandable
  source/factor-gap rationale. No global ranking, data semantics, or explicit
  add/reactivate command changed.

## 2026-07-13 · M1 partial Elendix source provenance

- The draft Elendix catalog now freezes two dated, hash-checked thread locators:
  one author-stated discount-rate explanation and one explicit risk/reward and
  investment-cycle question. They make partial evidence inspectable without
  treating a question as a rule or adding a company conclusion.
- Elendix remains draft for Discover, Research and Valuation. The version bump
  records the source-manifest change; no skill, required check, worker command,
  perspective, valuation template or synthesis is enabled until a fuller
  primary corpus receives an independent strict review.

## 2026-07-13 · M1 immutable snapshot-bound Malik/OBS perspectives

- Added a separate immutable `ResearchMethodPerspective` linked to one
  canonical Research snapshot without rewriting its profile, evidence, status,
  or history. An explicit user command freezes the full parent bundle and the
  retained Malik/OBS manifest, source hashes, locators, required checks, and
  contract fingerprint; identical commands reuse the same job.
- A claimed worker classifies each frozen check as supporting, contradicting,
  unknown, or not applicable, then records one separate conclusion only when
  the method applies. Supporting/contradicting evidence must be a factual or
  calculation claim tied to a non-lead parent source; assumptions and forum
  leads cannot become evidence. It cannot refresh, recommend, blend methods,
  or simulate the author. A distinct strict verifier owns final status and
  checks binding, attribution, applicability, unknown handling,
  non-impersonation, and no-hidden-blend.
- Research now renders each saved perspective separately and exposes an
  explicit “Utwórz perspektywę” action for the current snapshot. It does not
  execute the queued job. Areczeks and Elendix remain named draft blocks; no
  multi-method synthesis has been introduced.

## 2026-07-13 · M1 source-frozen Research method catalog

- Added a stage-aware, read-only method catalog to every canonical Research
  workspace. Malik/OBS exposes its retained source paths, SHA-256 hashes,
  exact locators, readiness, questions and blind spots without producing a
  company conclusion. The transcript's unknown original publication date stays
  explicit; local document metadata is not repurposed as source time.
- Areczeks and Elendix are rendered only as named draft packs with their source
  and implementation gaps. The catalog cannot queue work, invoke a model, make
  a recommendation, or create a hidden method blend.

## 2026-07-13 · R1 user-owned Research profile versions

- Added an explicit user profile command and Polish company-page editor for
  archetype, overlay, drivers and KPIs. Every confirmation or correction
  appends a `CompanyProfile` version with human/Codex provenance, author,
  reason and lineage; earlier profiles, evidence and snapshots are not
  rewritten.
- The Research workspace now distinguishes the profile bound to the canonical
  snapshot from the current profile and exposes immutable profile history. A
  pending human profile is visibly separate until an explicit review completes.
- Review jobs now freeze the selected profile's complete contents and
  fingerprint. Their idempotency key includes that fingerprint, and the
  verifier/save gate rejects any review draft that drifts from it.

## 2026-07-13 · D2 comparable Discover contract

- Replaced the financial-only Discover result list with a union of typed,
  per-sieve memberships. Each membership carries its local rank/factors/gaps,
  source and freshness; the shared candidate states exactly which sieves include
  it. There is no global opportunity rank.
- The UI now renders three comparable sieve columns and overlap indicators.
  Only the source-backed financial-health column has candidates today; OBS and
  Portal Analiz remain explicitly blocked with empty candidate references,
  null source/freshness and named market-wide data gaps.
- Added a frozen multi-sieve fixture that covers unique, paired and all-three
  overlap without claiming that the blocked providers have live data.

## 2026-07-12 · D1 Discover integrity and provenance

- Discover now rejects structurally incomplete or implausibly small first
  market-rating pages, plus a material (>30%) count drop or insufficient
  ticker continuity from a prior substantial good snapshot; failed refreshes
  retain their raw evidence and the stored read continues to serve the last
  parsed universe.
- The Discover contract and UI separate immutable content time, last successful
  source check, and the latest failed refresh. Stale lists remain visible but
  cannot present their ordering as current; the source version, report period,
  factor values/gaps, and explicit neutral-context unknowns are visible.
- A Discover admission freezes its sieve/version, parser/source identity,
  report period, membership factors, gaps, and context in the initial Research
  job. Closed cases can be reactivated from Discover, and an independent
  Research-list read failure no longer hides the stored Discover list.
- Replaced the misleading `rank_candidates` MCP tool with
  `assess_data_readiness`, which evaluates the full eligible stored-company set
  before applying its output limit.

## 2026-07-12 · Default GPW analysis workspace contract

- Refined the Product north star from a generic research second brain into the
  investor's default GPW analysis workspace, with one durable path from why a
  company deserves attention through business understanding, separate
  source-backed method perspectives, explicit scenarios, falsifiers, and real
  portfolio impact.
- Defined expert-derived methods as attributed, non-impersonating, stage-aware,
  versioned packs. Company evidence remains independent from method corpora;
  Codex may synthesize visible agreement and disagreement but may not create an
  anonymous expert consensus or hidden blend.
- Replaced the Roadmap's completed-stage evidence diary with active incremental
  outcome gates for Discover integrity and multi-sieve comparison, user-owned
  Research profiles, method perspectives, verified portfolio scenario coverage,
  a read-only Research agenda, and later point-in-time calibration. Existing
  data, artifact, calculation, queue, and verifier foundations remain in place.
- Documented current capability limits separately from planned outcomes. This
  contract update adds no runtime feature and does not present Roadmap work as
  implemented.

## 2026-07-12 · P4 immutable portfolio and verified review platform

- Completed primary Research coverage for all mapped real holdings with CRI at
  7.25%. The issuer collector scopes Creotech's periodic archive to
  `.investors-content__report`; official index/report versions `108/109` retain
  30 authorized links and 30 bounded report-page claims. Initial run 42 passed
  corrected VerificationRun 15; a subsequent independent code audit rejected
  fixed costs as sourced because the report does not split fixed and variable
  costs. Review run 43 preserved immutable history, passed VerificationRun 16
  and saved corrected snapshot/profile `13/12` as provisional. Working capital
  and capex are sourced; volume, price/mix, gross margin, fixed costs, backlog
  and three additional gaps remain explicit. The artifact separates continuing
  operations from spun-off Quantum, labels cash flow as combined, and preserves
  the KIMSF 17 presentation limitation.
- Continued real portfolio coverage with BFT at 10.00%. The issuer collector
  scopes Benefit Systems' current `.news-related-files`; official index/report
  versions `99/100` retain two links and 30 bounded report claims. Initial run
  41 passed VerificationRun 14 and saved snapshot/profile `11/10` as
  provisional. Volume, gross margin, working capital and capex are sourced;
  price/mix, fixed costs, backlog and four additional gaps remain explicit.
  MAC consolidation and the 109.8m PLN IAS 29 monetary gain are separated from
  organic operating interpretation.
- Continued real portfolio coverage with CBF at 10.05%. The bounded issuer
  collector scopes cyber_Folks' Q1 attachment block to `.attachments`;
  official index/presentation/statement versions `89/90/91` retain seven
  links and 30 bounded claims from each selected PDF. The oversized management
  report remained rejected by the 15 MB safety cap. Initial run 40 passed
  VerificationRun 13 and saved snapshot/profile `10/9` as provisional.
  Recurring revenue, NER-based revenue retention/expansion, wages and cash
  conversion are sourced; utilization and five additional gaps remain explicit.
- Continued real portfolio coverage with CDR at 10.27%. The bounded issuer
  collector now scopes CD PROJEKT's Q1 result-center entry to
  `.presstype-quarter .entry-content`; official index/report/presentation
  versions `79/80/81` retain three authorized links, 29 bounded report claims
  and all 16 presentation pages. Trusted scoped link generations
  `@4/@5/@6/@7` may authorize PDF fetches while older noisy lineage remains
  excluded. Initial run 39 passed corrected VerificationRun 12 and saved
  snapshot/profile `9/8` as provisional. Launch timing, cumulative units,
  pipeline and runway are sourced; price, concrete platform share and four
  further evidence gaps remain explicit. The first strict pass rejected total-
  IP labelling of product sales and digital-channel share used as platform
  share before persistence.
- Continued real portfolio coverage with DIG at 13.53%. The bounded issuer
  collector now scopes Digital Network's periodic-report archive to
  `.files-section`; official index/report versions `70/71` retain one Q1 link
  and 30 bounded page claims from the 52-page report. Trusted scoped link
  generations `@4/@5/@6` may authorize detail fetches while older noisy
  lineage remains excluded. Initial run 38 passed independent VerificationRun
  11 and saved snapshot/profile `8/7` as provisional. Five of seven
  industrial/consumer markers are sourced; fixed costs, backlog and four
  additional evidence gaps remain explicit. The result separates acquisition-
  driven reported growth from unknown organic growth and adds no valuation or
  portfolio assumptions.
- Continued real portfolio coverage with ART, the largest remaining uncovered
  holding at 14.37%. The bounded issuer collector now scopes Artifex Mundi to
  `.investors-page-content`; official landing/report versions `61/62` retain
  one report link and 13 page claims. Trusted scoped link generations `@4/@5`
  may authorize detail fetches while noisy legacy `@3` remains excluded.
  Initial run 37 passed corrected VerificationRun 10 and saved snapshot/profile
  `7/6` as provisional. Launch timing, platform share, pipeline and runway are
  sourced; sales units and price remain exact gaming-marker gaps, with four
  further evidence gaps. Alpha participants are explicitly not reported as
  unit sales. The first strict pass rejected a missing landing-page date source
  and fact-labelled archetype judgment before persistence.
- Added ASBIS to the bounded issuer-IR collector and ingested its official
  2026Q1 report as immutable source/index versions `52/53` with 24 page claims.
  The parser now scopes ASBIS extraction to article content so report-heavy
  navigation cannot create false links. Its empty same-host download redirect
  is upgraded to HTTPS under a narrow zero-length exception; the final PDF
  response still requires public DNS and connected-peer validation. Focused
  fixture tests cover both production shapes.
- ASB review run 36 bound prior snapshot 5 and the new primary evidence, then
  passed corrected independent VerificationRun 9 and saved snapshot/profile
  `6/5` as provisional. Four of seven industrial/consumer markers are now
  sourced: price/mix, gross margin, working capital and capex. Unit volume,
  fixed costs and backlog remain exact marker gaps; three additional evidence
  gaps and one USD/PLN translation conflict stay visible. The first strict pass
  rejected unsupported publication/price wording and an imprecise logistics
  description before anything was persisted.
- Began the real Research-coverage gate from immutable portfolio snapshot 2.
  ASB, the largest uncovered holding at 21.65%, completed v2 Research snapshot/
  profile/verification `4/4/7` after a strict-verifier rejection corrected
  overbroad consensus-source wording. Three of seven industrial/consumer
  markers are sourced; eight gaps keep it provisional. The older OPM run also
  completed as provisional legacy-v1 snapshot/profile/verification `3/3/6`
  after an independent rejection removed unsupported project/mix mechanisms
  and an ambiguous normalized margin series. Neither action synchronized or
  changed portfolio snapshot 2, and no scenario became eligible.
- Added explicit replacement Research for existing cases. One user command
  queues a content-idempotent `stock-company-review`, freezes the prior
  immutable snapshot plus current latest source identities, and leaves the
  prior snapshot readable while work waits. The claimed worker alone refreshes
  sources and may save the next sequential snapshot only through the unchanged
  independent verifier gate. Research list and company workspace expose the
  latest collection state; repeated identical commands do not duplicate jobs.
  Real ASB review run 35 froze snapshot 4 and source versions 45–51, found no
  new document version, passed independent VerificationRun 8 and saved
  snapshot 5/version 2 with profile 4 reused and an exact no-new-evidence
  history delta. The result correctly remains provisional with the same gaps.
  An independent implementation audit rejected and then closed two queue/save
  bypasses: the strict gate now rechecks frozen prior ID/artifact/source hash
  and immediate-latest identity, while the generic agent endpoint cannot create
  malformed company-review rows. The full backend suite and production build pass.
- Closed the real-provider integration gate with the exact portfolio `Kuba`.
  Parser-v2 snapshot 2 reconciles, retains complete provider history, maps all
  eight GPW holdings (one exact existing identity and seven explicit confirmed
  corrections) and reuses the same snapshot on an unchanged repeat sync.
  Mapping created no Research case or job. Portfolio review 1
  passed all nine strict checks in VerificationRun 5 and renders through
  canonical Company routes. Its status remains deliberately `provisional`:
  verified scenario coverage is 0%, seven holdings lack Research and SNT's
  valuation is provisional, so P4 remains open for evidence coverage rather
  than provider integration.
- Corrected the live myfund payload contract after the first accepted portfolio
  response: sequential `0..N-1` object keys now use stable instrument/account
  identities, `Konta gotówkowe` is recognized only as an exact provider type,
  and terminal PLN `Akcje GPW` codes drive safe matching. Explicit mapping may
  create only the matching minimal GPW Company and never a Research case/job.
  Snapshot cost/profit now sums complete current position rows instead of
  mislabelling the provider's flow-aware summary profit; incomplete rows yield
  null aggregates and an explicit gap. Parser contract advanced to v2. Portfolio
  links now use the mapped canonical Company ticker rather than the provider's
  display ticker, while preserving the raw label as context.

- Replaced the empty append/skip position ledger with migration `0026` and a
  provider-neutral portfolio model: durable sync attempts, explicit instrument
  mappings, immutable dated holdings/value history and immutable verifier-
  gated portfolio reviews. The legacy position API/panel was removed.
- Implemented explicit myfund synchronization through the documented API-key
  and exact portfolio-name contract. Reads are zero-write; failures are
  sanitized and durable, identical current content reuses the latest snapshot,
  and changed or later-reverted content receives the next version. Unknown
  rows remain visible and failed refreshes preserve the last good state.
- Added deterministic concentration/HHI, provider-labelled history and
  benchmark series, provisional 20-session liquidity, mapping/coverage gaps
  and point-in-time scenario sensitivity. Only verified valuations bound to
  the latest eligible Research enter the calculation; cash and uncovered value
  remain unchanged. TWR, XIRR and total-return benchmark claims remain blocked.
- Added the calm Portfolio page with a dominant holdings table, conditional
  attention, exact snapshot freshness, progressive history/scenario/method
  detail and honest configuration, empty, failure, unmapped, stale and
  uncovered states. Provider sync and Codex review are explicit buttons; page
  reads never perform either action.
- Added `stock-portfolio-review`: content-idempotent queueing freezes the exact
  snapshot, retained rows, current mappings, deterministic analytics/methods
  eligible valuation fingerprints and evidence-labelled Research/falsifier/
  co-exposure context. A separate strict verifier owns the immutable Polish
  review; exact model roles, fingerprints, known transaction-instruction
  language and look-ahead fail closed, while mapping drift can only finish as
  `needs-human`. Exact terminal save retries are idempotent.
- Derived analytics now fail closed when retained rows do not reconcile to the
  provider total. Malformed history is labelled partial, liquidity excludes
  future-known backfilled price rows, and shared downside is limited to named
  sector/archetype co-exposure rather than inferred correlation or covariance.
- Provider-native row keys now prevent display-ticker mapping collisions; list
  payloads use stable instrument/account identity hashes. Exact cash requires
  an explicit provider asset type, so company/fund names containing “cash”
  remain unmatched and correctable. Disclosed requested/actual model differences
  require a persisted substitution or escalation explanation.
- Added configured bearer validation for domain APIs while keeping health open,
  and documented the canonical sync/review actions and model routing. Focused
  portfolio contracts, 606 backend tests, the frontend production build,
  PostgreSQL migration `0026`, three skill validators and browser interaction
  pass. The live browser proves zero-write opening, explicit sync and an honest
  sanitized failure state without creating a snapshot.

## 2026-07-12 · P3 immutable scenario valuation

- Added migration `0025` and the canonical `ValuationSnapshot` vertical:
  zero-write workspace/preview/history reads, typed assumptions, content-
  idempotent serialized queueing, exact verification/save scripts and MCP
  adapters, versioned Malik/OBS method and industrial/software templates.
- Added `valuation-engine-v2`. It consumes only Research-manifest Facts known
  by the cutoff, rejects conflicting consumed versions and invalid prices,
  requires four consecutive quarters, treats capex as a positive outlay,
  leaves loss-making C/Z scenarios unpriced and separates own-history
  sensitivity. Final probabilities belong only to the strict verifier.
- Added a calm Valuation list and company workspace with explicit editable
  downside/base/upside assumptions, optional visible event path, deterministic
  preview, Codex queue action, Polish limitations, frozen-input audit and
  Research-to-Valuation navigation. Stale valuations never appear under a new
  Research snapshot.
- Kept Areczeks and Elendix blocked until dated source packs exist. Ordinary
  valuation drafting requests Terra high, complex cases may explicitly
  escalate to Sol high, and every final artifact requires an independent
  Sol-high verifier.
- Completed two real provisional pilots. SNT snapshot 1 / verification 3
  excludes the 256.562 mln PLN discontinued gain and yields 305.41 PLN weighted
  versus frozen 384.60 PLN at 40/45/15. ABS snapshot 2 / verification 4 yields
  78.11 PLN versus 87.80 PLN at 35/45/20. These are scenario evidence, not
  recommendations; upstream and scalar-lineage gaps remain visible.
- The initial independent audit rejected six integrity/UI defects before any
  pilot save. After corrections, a fresh verifier approved the implementation;
  585 backend tests, frontend production build, skill validation, PostgreSQL
  runtime checks and browser interaction pass.

## 2026-07-11 · P2 reproducible sieves and tailored research breadth

- Replaced frontend-owned Discover definitions with three typed backend sieve
  contracts. Financial-health v1 freezes Altman `>= 8` and Piotroski `>= 7`,
  exposes exact rules/source/parser/coverage, and yields 45 candidates from
  stored GPW version 31 (384 universe, 366 joint coverage). OBS and Portal
  Analiz stay visibly blocked with zero candidates and named data/source gaps.
- Added seven canonical, versioned archetype packs plus read-only CLI/MCP
  lookup. New research jobs freeze v2 skill/snapshot/profile/pack versions;
  every required marker maps exactly once to a matching sourced driver/KPI,
  explicit assumption, or matching gap. Bundles, mismatches, duplicates,
  evidence-gap overlap, unknown markers and missing scope are rejected.
- Kept legacy v1 jobs executable through an explicit picker/skill path and
  preserved the saved ABS provisional pack alias as read-only compatibility.
  The Research audit separates sourced markers, assumptions, gaps and missing
  scope and exposes driver/KPI source IDs or bases.
- Simplified Discover to three concise comparison cards, collapsing secondary
  factor groups and gaps. Candidate rows explain Altman and Piotroski in Polish
  and retain one `Dodaj do Research` action.
- Completed the real SNT second-archetype pilot as immutable
  snapshot/profile/verification `2/2/2`. Run 28 independently reproduced the
  exact source, dossier, calculation and archetype boundary before strict pass;
  final status is `provisional` with three sourced industrial markers and four
  exact marker gaps. Failed handoffs were rejected before save, and OPM run 22
  remained queued and untouched.
- Verified 569 backend tests, frontend production build, all three skill
  validators, runtime/DB invariants, independent code approval and browser QA
  of Discover, Research list, ABS/SNT differentiation and the v2 audit drawer.
- One non-material provenance basis inside the immutable SNT snapshot still
  names `research-snapshot-v1` while explaining that valuation is separate.
  The stored contract and audit metadata are v2; correct the wording in the
  next SNT snapshot rather than mutating history.

## 2026-07-11 · P1 immutable tailored Research vertical

- Added versioned `CompanyProfile` and immutable `ResearchSnapshot` persistence
  in migration `0024`, with fixed six-section Polish content, seven supported
  archetypes, typed drivers/KPIs/claims, source manifest, conflicts, gaps,
  next checks, history and exact statement provenance.
- Added read-only Research workspace/history and latest snapshot status APIs,
  plus one shared HTTP/MCP/JSON verification-and-save boundary.
- Split verification from save: a distinct verifier context records a verdict
  bound to the exact draft and server-derived frozen-input fingerprint; save
  accepts only that unchanged draft under the active lease. The verifier owns
  final status and any named evidence gap forces `provisional` rather than
  `verified`.
- Enforced company/source identity, source fetch cutoff, future/no-look-ahead,
  sequential versions, immediate history, exact replay/concurrency, frozen
  skill/version/output contract and non-self-verification gates.
- Replaced the company page's generic dossier-first presentation with the fixed
  tailored Research workspace. Profile, drivers, KPIs and gaps are visible;
  source IDs, statement provenance and verifier evidence stay in a collapsed
  audit. The legacy dossier is explicitly secondary, and rejected/needs-human
  artifacts are contained behind an audit-only warning.
- Completed the real ABS one-shot pilot: snapshot/profile/verification `1/1/1`,
  nine source versions, eight honest gaps, independent strict pass and final
  `provisional` status. The case moved to monitoring and the lease cleared;
  no second job or recurring worker ran.
- Verified 560 backend tests, frontend production build, PostgreSQL migration,
  skill validators and browser navigation from Research to the six-section ABS
  artifact and its provenance/verifier audit.

## 2026-07-11 · Product reset toward a research second brain

- Replaced overlapping north-star, design, architecture, scored-analysis,
  validation, handoff, archive, and 109-ID task documents with four binding
  contracts: Product, Architecture, Strategy, and Roadmap.
- Removed tracked screenshots/previews/mockups, obsolete archives and plans,
  the duplicate `pa-scraper` prototype/zip, generated strategy summaries, old
  worked examples, task artifacts, and tracked TypeScript build state. Parser
  fixtures and the raw OBS/BiznesRadar source material remain.
- Defined the product as `Discover -> Research -> Valuation -> Portfolio`, with
  `ResearchCase` as the canonical company memory, explicit side effects,
  non-destructive archival, deterministic calculations, and verifier-gated
  Codex artifacts.
- Defined honest three-sieve boundaries: BiznesRadar financial health first;
  Malik/OBS and PortalAnaliz value/catalyst sieves only after their required
  market-wide facts and source snapshots exist.
- Defined cost-aware model routing: no model for deterministic work, GPT-5.3
  high for mechanical extraction/testing, Terra high for ordinary research,
  Sol high for deep synthesis and strict verification, and ultra only after a
  concrete escalation trigger.
- Completed P0: Discover reads only stored evidence; source refresh is explicit;
  company/settings reads no longer scrape, log in, call a model, or claim work;
  startup is service-only; watchlist removal preserves research memory; and the
  Next proxy now supports PATCH.
- Removed the retired forecast-growth, index-exclusion, triage/promotion, and
  browser queue-claim surfaces. Deleted both paused Codex project automations
  (recurring queue worker and source collector), so no hidden task can revive
  the old orchestration.
- Delivered the green P1 entry slice: one atomic/idempotent Research API accepts
  a frozen Discover candidate or typed ticker, creates/reuses/reactivates the
  company and case, and queues exactly one company-bound initial job. The
  picker requests Terra-high company research plus a Sol-high strict verifier.
- Rebuilt Discover as three concise sieve definitions with only the sourced
  financial-health sieve active, domain factor labels, twelve initially visible
  candidates, and one `Dodaj do Research` action. Research now lists cases with
  honest job states; a completed draft is no longer labelled verified.
- Added and validated the `company-research` and `strategy-malik-obs` skills and
  rewrote the Workbench action/queue/thesis-review skills around explicit,
  one-shot execution. P1 remains open for typed/versioned ResearchSnapshot and
  CompanyProfile persistence, a save gate, tailored renderer, and pilot result.
- Retired 16 live local queue rows created implicitly by the old Discover GET
  path (one candidate scan and fifteen company-less initial jobs); source
  documents/facts were preserved.

## Foundation retained from the pre-reset implementation

- Polite BiznesRadar, PortalAnaliz, ESPI/EBI, issuer-IR, price, and myfund
  adapter foundations with parser fixtures.
- Immutable source/document/fact lineage, deterministic financial services,
  research-case and assumption primitives, provider-neutral job/audit records,
  queue leases, verifier boundaries, and no-look-ahead/price-identity guards.
- Local `./workbench` operator, FastAPI/SQLAlchemy/PostgreSQL backend, and
  Next.js same-origin API proxy.

## Permanent release rules

- Every code, schema, configuration, capability, or product-contract change
  adds a concise release entry here.
- User-facing flow changes update `skills/workbench-actions/SKILL.md` in the
  same patch.
- Model routing and independent verification are recorded in
  `docs/model-usage.md`.
