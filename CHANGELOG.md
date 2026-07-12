# Changelog

Release-level changes and durable decisions only. Granular history before the
product reset remains available in Git at and before `2ac75d0`.

## 2026-07-12 · P4 immutable portfolio and verified review platform

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
