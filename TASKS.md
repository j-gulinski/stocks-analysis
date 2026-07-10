# Implementation Tasks

Companion to `PLAN.md`. Each phase ends with a runnable increment. Check off as we go; IDs are stable for referencing in sessions ("do P1.3").

Every completed phase additionally gets a one-page learning note `docs/learning/phase-N.md` (PLAN §13) — concepts introduced, C# analogies, where to look in the code. Not listed per phase to keep this file about the build.

---

## Phase 0 — Scaffold

**Goal:** empty but running skeleton of everything.
**Done when:** `docker compose up` starts Postgres, backend serves `/api/health`, frontend renders a page, first Alembic migration applies.

- [x] P0.1 Repo layout per PLAN §2; move source docs into `docs/source-materials/`; `.gitignore` (`.env`, `node_modules`, `__pycache__`, `.next`)
- [x] P0.2 `docker-compose.yml` with postgres 16 + volume; `backend/.env.example` (DATABASE_URL, PA_USERNAME, PA_PASSWORD, ANTHROPIC_API_KEY, ANTHROPIC_MODEL)
- [x] P0.3 Backend skeleton: FastAPI app factory, `config.py` (pydantic-settings), `/api/health` (checks DB connection) — no CORS needed, browser talks only to the Next proxy
- [x] P0.4 SQLAlchemy setup + all models from PLAN §4 + initial Alembic migration
- [x] P0.5 Frontend skeleton: `create-next-app` (TS, App Router), SCSS setup (variables, globals, dark theme base), route-handler proxy `app/api/[...path]` → `BACKEND_URL` (localhost:8000 in dev), api helper (`src/lib/api.ts`) calling the proxy, empty watchlist page
- [x] P0.6 README: how to run backend, frontend, DB locally

## Phase 1 — Module B: BiznesRadar + prices

**Goal:** one command/endpoint fills the DB with full financials for a ticker.
**Done when:** for a real ticker (e.g. DEC or NVT) all statements Q+Y, indicators, dividends, profile and prices are in Postgres; parser tests green against fixtures.

- [x] P1.0 Shared fetch helper `scrapers/http.py`: per-domain rate limiter with randomized jitter (BR 2–4 s, PA 1.5–3 s), realistic UA, exponential backoff on 403/429/5xx + hard stop after repeated failures, `fetch_log` writes — **all scraper requests go through this**
- [ ] P1.1 *(synthetic fixtures committed + structural tests ready — run `python scripts/record_fixtures.py DEC` locally to record real pages)* Record fixtures: fetch and save real HTML for every page type from PLAN §6 (2 different companies — one GPW, one NewConnect); confirm URL patterns
- [x] P1.2 Generic `report-table` parser: headers/periods, rows, `span.value` extraction, number + period normalization, units (tys. PLN); unit tests on fixtures
- [x] P1.3 Statement scrapers: income (Q+Y), balance, cashflow → upsert into `report_values`
- [x] P1.4 Indicator scrapers: wskaźniki wartości rynkowej (C/Z, C/WK, EV/EBITDA history) + rentowności → `indicator_values`
- [x] P1.5 Dividends scraper → `dividends`; profile scraper (name, sector, shares outstanding) → `companies`
- [x] P1.6 `stooq.py`: daily CSV → `prices` (initial load + incremental by date)
- [x] P1.7 Refresh orchestration: `POST /api/companies/{ticker}/refresh?scope=&force=` — sequential fetch, ~2 s delay, 24 h cache via `fetch_log`, per-page error isolation (one failed page ≠ failed refresh)
- [x] P1.8 Read endpoints: `/financials`, `/indicators`, `/dividends`, `/prices` + watchlist CRUD (`/api/watchlist`)
- [~] P1.9 BiznesRadar premium session (user has an account): optional `BR_USERNAME/BR_PASSWORD`, login before fetches, longer histories; summary gains a `br_login` entry. **Scaffolded (config + `BrClient` + session threading + diagnostics + synthetic-fixture test); login-form parser UNVERIFIED — record a real BR login page + one live login on the user machine to finish.**

## Phase 2 — Module A: PortalAnaliz forum

**Goal:** forum threads linked to companies and synced incrementally.
**Done when:** linking a real thread URL pulls all posts; second sync fetches only new ones; posts readable via API.

- [x] P2.1 phpBB login with `.env` credentials (port logic from reference: form tokens, session cookies); login test endpoint for `/ustawienia`
- [x] P2.2 Thread parser: pagination, post_no, author, ISO timestamp, text + HTML (structure per reference scraper); fixture test on saved thread page
- [x] P2.3 Topic linking: `POST /api/forum/topics` {url, ticker} → resolve canonical topic id, store in `forum_topics`
- [x] P2.4 Sync: full first pull, incremental after (from max post_no); all requests via `scrapers/http.py` (jittered delays, backoff); `POST /api/forum/topics/{id}/sync`
- [x] P2.5 Read endpoint: `GET /api/companies/{ticker}/forum?page=&author=` (paginated, newest first)
- [~] P2.6 Post upvotes: `forum_posts.upvotes` (migration 0002), best-effort parser (selector list + text pattern), `sort=top` API + UI toggle; feeds AI token budgeting. **Mechanical synthetic tests pass; keep partial until `real/pa/topic.html` proves the actual PortalAnaliz vote markup.**

## Phase 3 — Module C backend: metrics, prescore, forecast, dossier

**Goal:** everything computed that the UI and the AI both need.
**Done when:** dossier endpoint for a refreshed ticker returns metrics matching hand-checked BiznesRadar numbers; forecast reproduces the Novita transcript example within rounding.

- [x] P3.1 `metrics.py`: quarterly series — revenue r/r, marża brutto na sprzedaży, sales margin after SG&A, net margin, operating leverage, one-off share; unit tests with hand-checked values
- [x] P3.2 TTM aggregates: net profit, EPS, market cap (latest price × shares), C/Z TTM; C/Z-vs-own-history stats (median, quartiles, current percentile)
- [x] P3.3 Net cash/debt from balance sheet; dividend continuity summary
- [x] P3.4 Deterministic prescore: 8 rules from PLAN §7, each → pass/fail/unknown + evidence numbers; JSON output shared by UI and AI prompt
- [x] P3.5 `forecast.py`: default assumptions derived from history (PLAN §7 table), pure compute → full forecast P&L, EPS, EBITDA, y/y comparison, forward C/Z; save/list scenarios (JSONB)
- [x] P3.6 `dossier.py` + `GET /api/companies/{ticker}` — single JSON: company, freshness, metrics series, TTM, prescore, latest forecast summary, forum stats (post count, last post)

## Phase 4 — Module C frontend: watchlist + stock pages

**Goal:** the app replaces the Excel workflow end to end.
**Done when:** you can add a ticker, refresh it, browse financials/charts, build and save a forecast, and read the forum — all in the UI.

- [x] P4.1 Layout: nav, dark SCSS theme with tokens from `docs/design/design.md`, loading/error states, PLN/percent formatters (`pl-PL`) — all Phase 4 UI follows `docs/design/mockups.html`
- [x] P4.2 Watchlist page: table per PLAN §7, add/remove ticker, refresh button with progress state, freshness indicator
- [x] P4.3 Stock page shell + **Przegląd** tab: key numbers, prescore checklist with evidence, price chart (recharts)
- [x] P4.4 **Finanse** tab: statement tables Q/Y with period columns (BiznesRadar-like layout)
- [x] P4.5 **Wykresy** tab: przychody, marża brutto %, zysk ze sprzedaży, zysk netto — quarterly sequence + y/y quarter grouping (his two Excel views)
- [x] P4.6 **Prognoza** tab: assumption form prefilled with defaults, live recompute, forward C/Z result vs historical C/Z range, save/load scenarios
- [x] P4.7 **Forum** tab: link-topic form, post timeline, author filter, pagination
- [x] P4.8 `/settings` (nav in English per user decision): status checks (DB, PA login, Anthropic key present)

## Stage TH — Investment-thesis layer (rule-based, pre-Phase-5)

**Goal:** per-stock investment-thesis read in Malik's spirit — weighted
pros/cons + entry-point quality + "what to check next", composed from the
computed dossier (pure functions, like `insights.py`). Entrance point for human
analysis, **not** a buy signal; **not** the Phase 5 Claude layer. Full spec:
`docs/plan-stage-thesis.md`.
**Done when:** `docs/strategy-malik.md` is source-cited; `thesis.py` +
`test_thesis.py` green in-session; `ThesisPanel` renders traceable numbers;
DGN/SNT + current-cap validation documented with gaps; memory/changelog updated.

- [x] TH.1 Source-grounded strategy spec `docs/strategy-malik.md` (≥5 primary
  web sources + reconcile 3 source-material files; every principle cited +
  mapped to a computed field or a labelled gap; entry-quality thresholds)
- [x] TH.2 Generic engine `services/thesis.py` + `services/strategies/`
  (`base.py` StrategyProfile/Criterion interface, `malik.py` profile-as-data,
  `cases.py` WorkedCase + evaluate_case) + `test_thesis.py` (in-session):
  entry quality, weighted pros/cons, `verify_next`, forward-C/Z preference,
  honest gaps, fabrication guard, toy-profile genericity test; wire into
  `dossier.py` + `api/schemas.py` (compile-check)
- [x] TH.2b Optional Claude-API iterative thesis refiner `services/thesis_ai.py`
  + config (`anthropic_max_iterations`, `ai_cache_enabled`) + `test_thesis_ai.py`
  (stub transport): **injectable transport** (anthropic SDK if importable →
  stdlib `urllib` POST → `StubTransport` in tests), bounded N-round refine of the
  WP2 read against the `WorkedCase` corpus + active profile, schema +
  fabrication-guard validation, JSON-file cache keyed by
  `(ticker, input-hash, model, profile-version)`, **no-key fallback** to the
  deterministic read with an `engine: deterministic|ai` marker; stub-tested paths
  (happy/malformed/iteration-limit/fabrication/convergence + cache), real-call
  smoke deferred to user (`ANTHROPIC_API_KEY=… python scripts/thesis_ai_smoke.py
  SNT`). Deterministic-first — does **not** replace Phase 5 (`skill/`/`analyses`/
  AI tab). Full spec: `docs/plan-stage-thesis.md` §WP2b
- [x] TH.3 `ThesisPanel.tsx` top of Overview (above InsightsPanel) + `types.ts`
  `Thesis`; as-is rendering, degraded states, disclaimer (build deferred to user)
- [x] TH.4 Validation `docs/validation-thesis.md`: DGN/SNT historical (with
  gaps, no fabricated figures) + ≥4 current small/mid/large caps, numbers
  cross-checked; archiwum page 1 only, quirks not re-derived; DGN/SNT recorded
  as `WorkedCase` entries *(in-session part done + verifier-approved: fixture
  pipeline + size-lens comparability + DGN/SNT `WorkedCase`s, documented with
  gaps per the rescoped WP4 acceptance #1. **Deferred to the user's machine**
  (sandbox has no egress): the live ≥4-ticker cross-check + DGN/SNT deep
  backtest via `cd backend && python scripts/validate_thesis.py DGN SNT …` —
  results append to `docs/validation-thesis.md`.)*
- [x] TH.5 Conformance + memory: in-session test subset green, `docs/learning/
  phase-thesis.md` (C# analogies), CLAUDE.md doc index + final CHANGELOG entry

## Stage SC — Scenario simulation engine (deterministic-first + AI)

**Goal:** per-stock simulation-based scenarios (negative/base/positive + event)
— each with coherent probability, data-grounded narrative, sector-relevant
target valuation (C/Z · C/WK · EV/EBITDA) off own + comparable multiple history,
repricing horizon, implied upside, and a probability-weighted EV vs current
price — plus an AI valuation agent (potential + confidence + what-would-change).
Extends the `thesis_ai.py` deterministic-first pattern; surfaced next to
`ThesisPanel`, framed as an analysis entry point, not a signal. Full spec:
`docs/plan-stage-scenarios.md`.
**Done when:** `scenarios.py`/`test_scenarios.py` + `scenarios_ai.py`/
`test_scenarios_ai.py` + `valuation_ai.py`/`test_valuation_ai.py` green
in-session; `ScenariosPanel` renders traceable numbers; corpus enriched with
sourced multiples/durations incl. ≥1 miss; validation + memory/changelog updated.

- [x] SC.1 Compact context: CLAUDE.md index + archive closed Stage-TH changelog
  entries into `docs/changelog-archive-thesis-2026-07-08.md` (quirks ledger left
  byte-identical); no code change
- [x] SC.2 Clean project: remove provably-dead code (per-item zero-reference
  grep proof in the CHANGELOG); full runnable test suite green as the safety proof
- [x] SC.3 Scenario engine: pure `services/scenarios.py` (multiple-reversion
  targets off own + corpus multiple history, Σ-prob=1, weighted EV) +
  `services/scenarios_ai.py` (bounded rounds, cache, fabrication guard over
  inputs∪engine∪corpus, no-key fallback) + `test_scenarios.py` (≥9) +
  `test_scenarios_ai.py` (≥10); wire `scenarios` block into `dossier.py`/
  `schemas.py`; `ScenariosPanel.tsx` + `types.ts`; `scripts/scenarios_smoke.py`
- [x] SC.4 AI valuation agent `services/valuation_ai.py` (potential + confidence
  + what-would-change; same guard/cache/fallback) + `test_valuation_ai.py` (≥8);
  enrich `strategies/cases.py` WorkedCase corpus with sourced multiples/durations
  incl. ≥1 documented miss (lazy CORPUS + import purity preserved); wire
  `valuation` block into dossier/schemas + panel/types
- [x] SC.5 Validation `docs/validation-scenarios.md` (hand-checked targets/EV,
  fixture-first, gaps explicit) + exact test counts + `docs/learning/
  phase-scenarios.md` (C# analogies) + CLAUDE.md index + final CHANGELOG entry

## Phase 5 — Module D: strategy skill + Claude analysis

**Goal:** one click → structured verdict on strategy alignment and potential.
**Done when:** analysis of a real watchlist stock returns valid schema, sensible Polish summary, stored history; verdicts reference actual evidence (numbers, forum posts).

**Reconciliation with Stage TH (TH.2b, 2026-07-08).** The Claude transport,
`.env` config, and response-cache pattern now exist from TH.2b's engine-level
thesis refiner (`services/thesis_ai.py`), and the dossier `thesis` block already
carries an `engine: deterministic|ai` marker. So **P5.4 (`claude_client.py`)
builds on / reuses that transport** rather than starting fresh. P5.1–P5.3
(skill/rubric/examples), P5.5 (prompt assembly for the full verdict + forum
distillation), P5.6–P5.7 (`analyses` table, endpoints, Analiza AI tab + history,
`AI_DAILY_LIMIT`), and P5.9 remain as-is — the Phase-5 *analysis product* is
distinct from TH.2b's thesis-block refinement. Tasks below are not rewritten.

- [x] P5.1 Author `skill/SKILL.md`: distill the 4 source docs (philosophy, 14-point checklist, 7 golden rules, catalyst taxonomy, one-off guidance, red flags, valuation via forward C/Z vs own history). **Draft done — review together before wiring it in (P5.4+)**
- [x] P5.2 `skill/rubric.md`: item weights → alignment_score 0–100; explicit "unknown ≠ fail" scoring rule
- [x] P5.3 `skill/examples/`: 2–3 worked examples distilled from obs.txt reasoning (real thesis → outcome) — OPTEX (win), TOYA (durable discount), Suntech (documented miss)
- [x] P5.4 `claude_client.py`: anthropic SDK, forced JSON output (tool use) with schema from PLAN §8, retries, token logging — `run_analysis` + `AnalysisUnavailable` (no deterministic fallback); 17 pure tests green
- [x] P5.5 `prompts.py`: system = SKILL.md + rubric; user = dossier JSON + token-capped recent forum posts + prescore; deterministic assembly (snapshot returned; note: not persisted — `analyses` table has no snapshot column)
- [x] P5.6 Endpoints: `POST /api/companies/{ticker}/analyses` (run), `GET .../analyses` (history); persist output + tokens + requesting user email; global `AI_DAILY_LIMIT` cap (429 with Polish message when hit) — no migration needed (`analyses` already in 0001); 4 client-gated tests deferred to user machine
- [x] P5.7 **Analiza AI** tab: run button, verdict card (score, thesis, catalysts, red flags, verify-next), history list with diff vs previous run — `AnalysisPanel`, tsc green
- [ ] P5.8 Calibration pass — **superseded by RT.6**. Do not tune a skill to
  3–4 familiar winners. Build mixed-outcome training + untouched holdout cases,
  then use the judge loop and walk-forward protocol below.
- [x] P5.9 Forum distiller (PLAN §8): batched cheap-model pass over already-synced posts → per-post cached claims {type, claim, confidence, source post ids}; upvote-weighted ordering within token budget; zero extra forum requests; verdict prompt consumes claims, never raw posts as facts — file cache, 15 pure tests

## Stages RT.0–RT.7 — Research-platform roadmap (binding next work)

**Goal:** evolve the completed first vertical slice into the evidence-first,
company-specific research workflow in `docs/plan-research-platform.md`.
Deployment is RT.7, after the local pilot proves provenance, scenarios and
evaluation. IDs below are stable.

### RT.0 — Trustworthy baseline

- [x] RT0.1 Fix the two currently failing backend tests and prove the full suite
  is green without weakening assertions; document why fixture/current-price
  expectations drifted.
- [~] RT0.2 Reproduce frontend from a clean install (`npm ci`, typecheck,
  production build); add a minimal browser smoke test for add → refresh → stock
  brief → forecast/scenario → analysis history. **Clean install/build/audit and
  manual browser smoke are green; persist the automated Playwright path after
  the RT.4 workflow contracts replace the current overlapping views.**
- [ ] RT0.3 Finish real-fixture gaps: two companies for every BR page type, real
  BR login form/session, real PA upvote markup and parser tests. **Recorders now
  preserve ticker-specific companies, require the profile's canonical slug,
  cover all nine BR page types and connect the PA real fixture to tests; the
  actual two-company/login/upvote captures still require live source access.**
- [~] RT0.4 Add one `doctor` command/report covering DB, backend, frontend,
  credentials, source reachability and model providers; run one documented
  end-to-end local pilot. **`doctor/start/status/stop` and a stored-data browser
  pilot are complete; a live refresh pilot waits on RT0.3 real-source gaps.**
- [x] RT0.5 Reconcile README/PLAN/TASKS with actual commands, routes and source
  chain; remove stale Yahoo/stooq/Claude-only claims.

### RT.1 — Explicit, reproducible AI runs

- [x] RT1.1 Remove `thesis_ai`, `scenarios_ai` and `valuation_ai` calls from
  `build_dossier`; GET endpoints are deterministic, side-effect-free and tested
  to make zero provider calls.
- [~] RT1.2 Add analysis-run provenance + `model_calls`: status/purpose/as-of, complete
  input snapshot, evidence ids, skill hash/version, provider/model/config,
  validation, tokens/cost/latency, retries/escalation and user. **Core run and
  verdict-call provenance extend the current `analyses` table without
  overwriting a conflicting pilot `analysis_runs` contract; child distillation attempts, exact
  retry rows and price-based cost calculation move into RT1.3/RT1.6.**
- [~] RT1.3 Introduce a single run orchestrator + provider interface; migrate
  existing Anthropic calls behind it before adding OpenAI. Replace file-only
  production caches with durable hash/idempotency records. **The verdict path
  now uses `analysis/orchestrator → executor → AnthropicProvider`, supports
  scoped `Idempotency-Key`, durable validated request reuse and per-attempt
  rows. Legacy direct-client compatibility and forum distillation still need
  migration before OpenAI is added.**
- [~] RT1.4 Define strict Pydantic output contracts and validate before
  persistence/rendering. Handle refusal, truncation, malformed evidence and
  stale run states explicitly. **Strict/no-coercion validation, stable ids,
  cache revalidation, failed/succeeded/stale recovery and distinct provider
  truncation/refusal/invalid-output states are implemented; material claim to
  evidence-id enforcement remains RT2/RT5.3.**
- [~] RT1.5 Compute strategy score/vetoes and all financial math
  deterministically. Models produce evidence-linked interpretations, not the
  authoritative number. **Alignment weights, unknown handling and current
  vetoes are server-owned and tested; future company-template/scenario math
  remains RT3–RT4.**
- [~] RT1.6 Add async job progress/cancellation and quota/cost accounting for
  every child call; hidden refiners cannot bypass the limit. **Verdict attempts
  record heartbeat/status/cache/billed/token/latency data. Atomic UTC-day run,
  provider-attempt and measured-token limits include retries; zero disables a
  budget, and stale work is claimed once and conservatively marked
  unknown-billed. Hidden forum model calls stay disabled until migrated.
  Monetary price snapshots/reservations, async progress/cancellation and every
  future child role remain.**

### RT.2 — Point-in-time evidence ledger + primary disclosures

- [~] RT2.1 Migrate immutable source documents/versions, typed facts with
  `known_at` + page/section locator, events and explicit data conflicts.
  **Migration `0008` adds the complete ledger contracts; BR report/indicator
  versions, typed facts and cross-document conflicts are active. Official
  event ingestion and object storage remain.**
- [~] RT2.2 Make current report/indicator serving rows traceable to source facts;
  refresh appends versions and supports an `as_of` read instead of destroying
  historical truth. **New report/indicator rows carry immutable fact pointers;
  identical content deduplicates, changed/failed versions are preserved, and
  point-in-time APIs select the latest complete parsed version per document.
  Legacy rows remain honestly unlinked until refreshed.**
- [ ] RT2.3 Pilot issuer-IR and official ESPI/EBI ingestion for 3–5 watchlist
  companies: periodic/current reports, guidance, material contracts/backlog,
  buybacks, dilution and management/shareholder events.
- [ ] RT2.4 Build source-quality/terms/rate notes and parser fixtures; material
  case claims must cite immutable source spans.
- [ ] RT2.5 Evaluate one corporate-action-aware, long-history market-data source
  against GPW coverage, licensing, delistings and total-return needs before
  choosing it.

### RT.3 — Fundamental depth + company templates

- [~] RT3.0 Add a low-request market discovery funnel. **One cached, immutable
  BiznesRadar GPW rating document now seeds transparent candidates with report
  period, Altman EM-Score rating and Piotroski F-Score; missing values remain
  missing and the UI explicitly withholds strategy-fit claims. Template-aware,
  point-in-time filters for liquidity, growth, margins, cash conversion,
  leverage and own-history valuation remain after RT3.1–RT3.3.**
- [ ] RT3.1 Compute operating cash flow vs profit, cash conversion, capex
  intensity, working-capital/receivables/inventory trends, ROIC/ROE where valid,
  share-count dilution and normalized one-offs.
- [ ] RT3.2 Add segment/geography/KPI facts and a versioned `CompanyTemplate`
  contract: required evidence, driver tree, scenario equations, valuation views,
  red flags and optional external series.
- [ ] RT3.3 Implement and hand-check 2–3 templates selected from real watchlist
  archetypes; deterministic selection plus visible user override.
- [ ] RT3.4 Add relevant official macro/sector adapters only for a template that
  consumes them (first candidates: NBP, GUS, PSE/URE); no generic macro feed.

### RT.4 — Research case + operating-driver scenarios

- [ ] RT4.1 Persist research-case state, blockers, thesis/counter-thesis,
  catalysts, falsifiers, next checks, user decisions and version history.
- [ ] RT4.2 Scenario engine v2: template driver assumptions → statements/cash
  flow/balance bridge → valuation → equity value/share; pure math with unit and
  sensitivity tests.
- [ ] RT4.3 Track each assumption as sourced fact, human assumption or model
  suggestion. Model suggestions and probabilities require user approval.
- [ ] RT4.4 Move current own-history multiple reversion into a valuation
  sensitivity; show unweighted ranges alongside probability-weighted values.
- [~] RT4.5 Rework stock UI around Evidence, Business, Performance, Thesis,
  Scenarios, AI review and Journal; show fact/thesis/scenario changes after a
  new report instead of multiple overlapping verdict cards. **The first slice
  consolidates the duplicated Brief, moves full scenarios out, reframes AI as
  Review and separates Evidence/Financials. Persistent case changes,
  Business/Thesis editing and Journal remain.**
- [~] RT4.6 UI/UX overhaul: audit existing screens/task flows; create and approve
  research-workspace wireframes + updated design tokens; implement a persistent
  case header, progressive workflow/navigation, evidence provenance states,
  non-blocking run progress, scenario driver/valuation bridge editor and strong
  empty/error/conflict states. **Three independent UX reviews converged on the
  new `docs/design/research-workspace.md`; Discover, Research, compact Brief,
  progressive workflow tabs, higher-contrast typography and mobile table
  containment are implemented. The case-state contract, evidence drawer and
  driver editor remain.**
- [~] RT4.7 Verify industrial, financial and event-driven cases at desktop and
  mobile widths with Playwright interactions/screenshots plus accessibility,
  keyboard, contrast and `pl-PL` formatting checks. Store the approved design
  spec in `docs/design/`; do not treat visual polish as proof of analytical
  correctness. **Manual in-app browser QA is green at 1280 px and 390 px for
  Discover, Research, all five SNT workflow tabs and raw table containment;
  automated screenshots, keyboard/axe checks and representative financial/
  event-driven cases remain.**

### RT.5 — OpenAI orchestration + Codex-facilitated workflow

- [ ] RT5.1 Add OpenAI Responses API adapter with strict structured outputs,
  background jobs and versioned skill attachment. Configure models by role
  (classify/extract/verify/analyze/adjudicate/judge), never as a hard-coded
  “latest” id. Include GPT-5.3 as a user-approved bounded-loop candidate when
  available, plus smaller model candidates for simpler work.
- [ ] RT5.1b Implement `ModelPolicy` per role: ordered allowed models, reasoning
  level, max calls/iterations/tokens/cost/timeout and explicit escalation
  conditions; enforce a run-level budget and persist the selection reason.
- [ ] RT5.2 Implement bounded cheap-model extraction/verification loops:
  deterministic schema/unit/period/arithmetic/citation checks → retry failed
  fields only → strong-model or human escalation. Test whether independent
  cheap passes add value; never equate self-agreement with correctness.
- [ ] RT5.3 Add prompt-injection isolation for untrusted source documents and
  evidence-id requirements for all material claims.
- [~] RT5.4 Build an idempotent `workbench` CLI: `doctor`, `start`, `stop`,
  `status`, `refresh`, `case`, `analyze`, `feedback`, `backtest`. **The four
  operator commands are implemented; add research commands with their RT.2–RT.6
  domain contracts rather than wrapping unstable endpoints early.**
- [~] RT5.5 Create `skills/workbench-research/SKILL.md` so a Codex task starts
  or checks the app when asked to research a company, facilitates the case
  stages, reports blockers and opens the relevant UI. Keep `skill/SKILL.md` as
  the investment-analyst skill. **The operator/research skill is created,
  validated and forward-tested for the commands that exist; extend its case
  workflow only as the remaining CLI contract lands.**
- [ ] RT5.6 After the CLI stabilizes, expose the same typed contract through an
  optional MCP/plugin; do not make Codex UI automation the only interface.

### RT.6 — Seasoned-investor judge + evaluation/backtest

- [ ] RT6.1 Build gold data/extraction/scenario cases with mixed outcomes and a
  failure taxonomy; split training/calibration from untouched holdout cases.
- [ ] RT6.2 Create a versioned `seasoned-investor-judge` skill and structured
  rubric: source correctness, accounting/units/periods, template choice,
  thesis/counter-thesis/falsifiers, scenario coherence, uncertainty,
  company-specificity, missing-evidence detection, usability, cost and latency.
  Judge input should be a compact validated trace plus disputed spans so its
  own cost stays proportionate.
- [ ] RT6.3 Build an isolated evaluator that launches the app, waits for health,
  seeds a frozen `as_of` case, drives the public CLI/API plus a small Playwright
  user path, runs scenarios/cheap models and captures the full trace for the
  judge.
- [ ] RT6.4 Implement the bounded improvement loop: judge failure labels →
  candidate prompt/template/validator/routing change in an experiment → replay
  training → replay holdout → cost/regression report → explicit user approval
  before versioned promotion. Judge never edits production directly.
- [ ] RT6.5 Add AI trace/dataset evals and regression gates; use batch processing
  for non-urgent large evaluation jobs when cost-effective.
- [ ] RT6.6 Add point-in-time walk-forward case replay with 3/6/12/24-month
  total/benchmark-relative return, adverse excursion, thesis-break timing and
  probability calibration. Require publication timestamps, corporate actions,
  delistings and no future leakage.
- [ ] RT6.7 Consider market-wide factor backtesting/weight tuning only after the
  case replay is credible; keep a final out-of-time holdout.

## RT.7 / legacy Phase 6 — Deploy & polish (Vercel + Railway, Google allowlist)

**Goal:** app live for you and allowlisted friends; everyone else hits a login wall.
**Done when:** friend signs in with Google on the Vercel URL and runs the full workflow; non-allowlisted account is rejected; direct Railway URL without token returns 401; DB backup restores locally.

**Scheduling decision (2026-07-09):** these tasks remain useful, but execute
after RT.0–RT.6 prove the local research workflow. Adapt deploy topology for
durable source documents, background analysis jobs and run traces before RT.7.

- [ ] P6.1 Backend Dockerfile + Railway: service from repo, managed Postgres plugin, env vars (PLAN §9), `alembic upgrade head` on release, healthcheck on `/api/health`
- [ ] P6.2 Backend auth middleware: require `Authorization: Bearer $API_TOKEN` when set (skip when unset = local dev); read `X-User-Email` into request context for analyses/forecasts attribution
- [ ] P6.3 Auth.js on frontend: Google provider, `signIn` callback checks `ALLOWED_EMAILS`, middleware guards all pages, `/api/auth/*` excluded from proxy; login page (Polish) + user menu with sign-out
- [ ] P6.4 Proxy hardening: attach bearer token + `X-User-Email` server-side; deploy frontend to Vercel (envs, prod `BACKEND_URL`), verify end to end with a second Google account
- [ ] P6.5 Backups: `pg_dump` script against Railway `DATABASE_URL` + restore-locally instructions; document env setup for both dashboards in README
- [ ] P6.6 Housekeeping: error toasts, empty states, refresh-all-watchlist button
- [ ] P6.7 (Optional/extension) Nightly watchlist + forum refresh via Railway cron hitting an internal refresh endpoint

---

## Extension backlog

Template-aware market-wide screener after the source-seed MVP · portfolio/position/risk module ·
forum topic auto-discovery · full-thread evidence-aware summarization · alerts ·
additional company templates and non-GPW markets · home/VPS ingestion agent if
cloud IPs are blocked. ESPI/EBI, Playwright workflow checks and honest
walk-forward evaluation are no longer extensions; they are RT.2/RT.0/RT.6.
