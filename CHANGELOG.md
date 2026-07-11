# Changelog

Release-level changes and durable decisions only. Granular history before the
product reset remains available in Git at and before `2ac75d0`.

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
