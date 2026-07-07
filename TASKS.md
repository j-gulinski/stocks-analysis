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
- [ ] P1.9 BiznesRadar premium session (user has an account): optional `BR_USERNAME/BR_PASSWORD`, login before fetches, longer histories; needs a recorded login-page fixture first; summary gains a `br_login` entry

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

## Phase 5 — Module D: strategy skill + Claude analysis

**Goal:** one click → structured verdict on strategy alignment and potential.
**Done when:** analysis of a real watchlist stock returns valid schema, sensible Polish summary, stored history; verdicts reference actual evidence (numbers, forum posts).

- [ ] P5.1 Author `skill/SKILL.md`: distill the 4 source docs (philosophy, 14-point checklist, 7 golden rules, catalyst taxonomy, one-off guidance, red flags, valuation via forward C/Z vs own history). Review together before wiring it in
- [ ] P5.2 `skill/rubric.md`: item weights → alignment_score 0–100; explicit "unknown ≠ fail" scoring rule
- [ ] P5.3 `skill/examples/`: 2–3 worked examples distilled from obs.txt reasoning (real thesis → outcome)
- [ ] P5.4 `claude_client.py`: anthropic SDK, forced JSON output (tool use) with schema from PLAN §8, retries, token logging
- [ ] P5.5 `prompts.py`: system = SKILL.md + rubric; user = dossier JSON + token-capped recent forum posts + prescore; deterministic assembly (snapshot stored with analysis)
- [ ] P5.6 Endpoints: `POST /api/companies/{ticker}/analyses` (run), `GET .../analyses` (history); persist output + tokens + requesting user email; global `AI_DAILY_LIMIT` cap (429 with Polish message when hit)
- [ ] P5.7 **Analiza AI** tab: run button, verdict card (score, thesis, catalysts, red flags, verify-next), history list with diff vs previous run
- [ ] P5.8 Calibration pass: run on 3–4 stocks you know well; tune SKILL/rubric until verdicts match your judgment of obvious cases
- [ ] P5.9 Forum distiller (PLAN §8): batched cheap-model pass over already-synced posts → per-post cached claims {type, claim, confidence, source post ids}; upvote-weighted ordering within token budget; zero extra forum requests; verdict prompt consumes claims, never raw posts as facts

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
