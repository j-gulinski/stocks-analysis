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
- [x] P2.6 Post upvotes: `forum_posts.upvotes` (migration 0002), best-effort parser (selector list + text pattern — verify against a recorded real page), `sort=top` API + UI toggle; feeds AI token budgeting

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
- [ ] P5.8 Calibration pass: run on 3–4 stocks you know well; tune SKILL/rubric until verdicts match your judgment of obvious cases
- [x] P5.9 Forum distiller (PLAN §8): batched cheap-model pass over already-synced posts → per-post cached claims {type, claim, confidence, source post ids}; upvote-weighted ordering within token budget; zero extra forum requests; verdict prompt consumes claims, never raw posts as facts — file cache, 15 pure tests

## Phase 6 — Deploy & polish (Vercel + Railway, Google allowlist)

**Goal:** app live for you and allowlisted friends; everyone else hits a login wall.
**Done when:** friend signs in with Google on the Vercel URL and runs the full workflow; non-allowlisted account is rejected; direct Railway URL without token returns 401; DB backup restores locally.

- [ ] P6.1 Backend Dockerfile + Railway: service from repo, managed Postgres plugin, env vars (PLAN §9), `alembic upgrade head` on release, healthcheck on `/api/health`
- [ ] P6.2 Backend auth middleware: require `Authorization: Bearer $API_TOKEN` when set (skip when unset = local dev); read `X-User-Email` into request context for analyses/forecasts attribution
- [ ] P6.3 Auth.js on frontend: Google provider, `signIn` callback checks `ALLOWED_EMAILS`, middleware guards all pages, `/api/auth/*` excluded from proxy; login page (Polish) + user menu with sign-out
- [ ] P6.4 Proxy hardening: attach bearer token + `X-User-Email` server-side; deploy frontend to Vercel (envs, prod `BACKEND_URL`), verify end to end with a second Google account
- [ ] P6.5 Backups: `pg_dump` script against Railway `DATABASE_URL` + restore-locally instructions; document env setup for both dashboards in README
- [ ] P6.6 Housekeeping: error toasts, empty states, refresh-all-watchlist button
- [ ] P6.7 (Optional/extension) Nightly watchlist + forum refresh via Railway cron hitting an internal refresh endpoint

---

## Extension backlog (explicitly not v1)

Screener over prescore for the whole GPW · forum topic auto-discovery · full-thread AI summarization cache · **ESPI/EBI poller + e-mail alerts for watchlist** (PLAN §10) · **hotness score 0–100 with self-learning backtests** (PLAN §10 — parked until production base is stable) · price alerts · US stocks (stockanalysis.com) · Playwright smoke tests · scraping from home machine/VPS pushing to the same DB (if cloud IPs ever get blocked) · per-user AI quotas
