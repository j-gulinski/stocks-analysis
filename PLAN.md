# Stock Analysis Workbench — Project Plan

Personal tool that aggregates data about GPW companies (BiznesRadar financials + PortalAnaliz forum threads), presents it the way Paweł Malik / OBS works in Excel, and uses a codified "strategy skill" (via Claude API) to assess whether a stock aligns with the strategy and has potential.

**Guiding principles:** simple first, no overengineering. Every module is a separately buildable, separately testable part with a clear interface. Extension points are documented, not pre-built.

---

## 1. Strategy → features mapping

What the source materials describe, and what in the app covers it:

| Strategy element (source docs) | App feature |
|---|---|
| "Nie kupuję spółek bez analizy sprawozdań" — quarterly RZiS as starting point | Financials tab: quarterly/annual income statement, balance sheet, cash flow (Module B + C) |
| Gross sales margin (marża brutto na sprzedaży) tracked quarterly in Excel charts | Metrics engine + Charts tab replicating his Excel "Wykresy" sheet (Module C) |
| Next-quarter forecast built by hand in Excel (transcript workflow) | Forecast module: assumption inputs → forecasted net profit, EPS, forward C/Z (Module C) |
| Forward C/Z compared to the company's **own** historical C/Z | C/Z history from BiznesRadar indicators + forward C/Z from forecast (Modules B + C) |
| Catalyst identification, investment thesis, one-off vs sustainable improvement | AI analysis with strategy skill (Module D) |
| Thesis re-verification after each quarterly report | Analysis history per company, re-run and compare (Module D) |
| Net cash surplus, backlog, dividend as a plus | Net cash computed from balance sheet; dividends scraped; backlog assessed by AI from forum/reports (B, C, D) |
| Management credibility, corporate governance red flags | AI reads forum discussion (PortalAnaliz threads) (Modules A + D) |
| Small/mid cap focus (sWIG80, NewConnect) | Market cap shown; small-cap check in scoring (C, D) |
| Forum as idea source and discussion context | Forum tab: full thread timeline per company (Module A) |

## 2. Architecture

```
┌─────────────────────────────┐
│  Frontend — Next.js + SCSS  │  watchlist · stock pages · forecast editor · AI verdicts
└────────────┬────────────────┘
             │ REST (JSON)
┌────────────┴────────────────┐
│  Backend — FastAPI (Python) │
│  ├─ scrapers/portalanaliz   │  Module A (phpBB login, thread sync)
│  ├─ scrapers/biznesradar    │  Module B (financials, indicators, dividends)
│  ├─ scrapers/stooq+yahoo    │  Module B (price history; BR archiwum is the reliable leg)
│  ├─ services/metrics        │  Module C (computed metrics, prescore)
│  ├─ services/forecast       │  Module C (Excel-workflow forecast engine)
│  ├─ analysis/               │  Module D (skill prompt assembly, Claude API)
│  └─ api/                    │  routers
└────────────┬────────────────┘
             │ SQLAlchemy
┌────────────┴────────────────┐
│  PostgreSQL (docker)        │  single source of truth; scrape once, read many
└─────────────────────────────┘
```

Principles:
- Scrapers only fetch + parse + upsert. No business logic inside scrapers.
- Metrics/forecast are pure functions over DB data — easy to unit test.
- AI layer consumes the same dossier JSON the frontend uses. One aggregation, two consumers.
- Local dev runs everything on localhost (Postgres via docker-compose). Production: frontend on Vercel, backend + Postgres on Railway as a long-running container — scrapers, delays and in-memory sessions work unchanged. Access limited to you and friends via Google sign-in allowlist (see §9a).

### Repo layout (monorepo)

```
stocks-analyzis/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, router registration
│   │   ├── config.py            # pydantic-settings, reads .env
│   │   ├── db/                  # engine, session, models.py, alembic/
│   │   ├── scrapers/
│   │   │   ├── http.py          # single fetch path: rate limiter + jitter, UA, backoff, fetch_log
│   │   │   ├── biznesradar.py
│   │   │   ├── portalanaliz.py
│   │   │   └── stooq.py
│   │   ├── services/
│   │   │   ├── metrics.py       # computed metrics + deterministic prescore
│   │   │   ├── forecast.py      # forecast engine
│   │   │   └── dossier.py       # aggregates everything for one company
│   │   ├── analysis/
│   │   │   ├── claude_client.py
│   │   │   └── prompts.py       # assembles skill + dossier + forum context
│   │   └── api/                 # routers: watchlist, companies, forum, analyses
│   ├── tests/
│   │   └── fixtures/            # recorded real HTML pages
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/app/                 # Next.js App Router pages
│   ├── src/components/
│   ├── src/lib/api.ts           # typed fetch helpers
│   └── src/styles/              # SCSS: variables, globals, modules per component
├── skill/
│   ├── SKILL.md                 # the codified Malik/OBS strategy (analyst instructions)
│   ├── rubric.md                # checklist items, weights, scoring rules
│   └── examples/                # worked examples distilled from obs.txt
├── docker-compose.yml           # postgres for local dev (production = Vercel + Railway)
├── PLAN.md · TASKS.md · CLAUDE.md
└── README.md
```

Note on `pa-scraper.zip`: treated as **reference only**. The phpBB login/pagination logic and the BiznesRadar table parsing proved workable — that knowledge gets ported into the new backend, the code itself is not reused as-is.

## 3. Tech stack

| Choice | Why |
|---|---|
| Next.js (App Router) + SCSS modules | Requested. SSR not needed but Next gives routing/structure for free; SCSS per component + shared variables |
| FastAPI + Pydantic | Requested Python; typed request/response models double as documentation |
| PostgreSQL in docker-compose | Chosen; JSONB for forecasts/analyses, proper upserts for scraped series |
| SQLAlchemy 2 + Alembic | Plain ORM + migrations — minimum viable maintainability for an evolving schema |
| requests + BeautifulSoup | Proven against both sites by the reference scraper; no browser automation needed |
| anthropic Python SDK | Module D; model set via config (default `claude-sonnet-4-6`) |
| recharts (frontend) | Simple quarterly bar/line charts like his Excel "Wykresy" sheet |
| Auth.js (NextAuth) + Google provider | Friends log in with Google; allowlisted emails only; added in deploy phase — local dev stays open |
| Vercel (frontend) + Railway (backend, Postgres) | Free/cheap (~$5/mo), zero server admin, backend stays a normal long-running process |

Deliberately **not** used in v1: task queues (Celery), schedulers, Redis, auth frameworks, GraphQL, ORM-generated APIs. Extension points exist for a scheduler and screener (see §10).

## 4. Data model (PostgreSQL)

Long/narrow format for scraped series — new fields on BiznesRadar don't require migrations:

- `companies` — id, ticker (uq), name, market (GPW/NC), sector, shares_outstanding, updated_at
- `report_values` — company_id, statement (`income|balance|cashflow`), freq (`Q|Y`), period (e.g. `2025Q3`), field_code, field_label, value (numeric, tys. PLN), scraped_at · **PK** (company_id, statement, freq, period, field_code)
- `indicator_values` — company_id, indicator (`cz`, `cwk`, `ev_ebitda`, …), period, value — historical C/Z etc.
- `dividends` — company_id, year, dps, yield_pct
- `prices` — company_id, date, close, volume (stooq daily CSV)
- `forum_topics` — id, company_id (nullable), url (uq), title, last_post_at, last_synced_at
- `forum_posts` — id, topic_id, post_no, author, posted_at, content_text, content_html · unique (topic_id, post_no)
- `watchlist_items` — company_id (uq), note, added_at
- `forecasts` — id, company_id, label, assumptions JSONB, result JSONB, created_at
- `analyses` — id, company_id, created_at, model, prescore JSONB, output JSONB, alignment_score, input_tokens, output_tokens
- `fetch_log` — url, status, fetched_at (politeness/debugging; also powers "data freshness" in UI)

## 5. Module A — PortalAnaliz scraper

Independent package: `scrapers/portalanaliz.py`. Rewrite informed by the reference implementation.

- phpBB login with credentials from `.env` (session held in memory; never stored in DB).
- Topic linking: v1 = user pastes thread URL(s) on the stock page ("Powiąż wątek"). A company can have several topics. Auto-discovery via forum search = extension, not v1.
- Incremental sync: store max post_no per topic, fetch only new pages since; first sync pulls full history.
- Parse: author, ISO timestamp, text + HTML (structure known from reference: `div.post` → `a.username-coloured`, `time[datetime]`, `div.content`).
- Politeness: ≥1.5 s between requests, custom UA, exponential backoff on non-200.

API: `POST /api/forum/topics` (link URL to company) · `POST /api/forum/topics/{id}/sync` · `GET /api/companies/{ticker}/forum?page=`

## 6. Module B — BiznesRadar scraper

Independent package: `scrapers/biznesradar.py`. One generic `report-table` parser reused across pages (they share structure):

| Page (URL pattern) | Data |
|---|---|
| `raporty-finansowe-rachunek-zyskow-i-strat/{T}` (+`,Y`) | Income statement Q/Y |
| `raporty-finansowe-bilans/{T}` | Balance sheet |
| `raporty-finansowe-przeplywy-pieniezne/{T}` | Cash flow |
| `wskazniki-wartosci-rynkowej/{T}` | Historical C/Z, C/WK, EV/EBITDA… |
| `wskazniki-rentownosci/{T}` | ROE, ROA, margin history |
| `dywidenda/{T}` | Dividend history |
| company profile page | Name, sector, shares outstanding, market cap |

First implementation step: **record real HTML of every page type into `tests/fixtures/`** and verify selectors against them (URL patterns above to be confirmed then — plain fetch returned empty here, but reference scraper confirms requests+bs4 works).

- Number normalization: `12 345` → 12345.0, values in tys. PLN, strip r/r change spans, handle empty cells.
- Period normalization: `2025/Q3` → `2025Q3`; annual `2024` → freq `Y`.
- Upsert keyed on (company, statement, freq, period, field) — refresh is idempotent.
- Cache policy: skip refetch if page scraped < 24 h ago unless `force=true`.
- Politeness: ~2 s between page fetches, sequential only (watchlist scale: ~7 pages per company).
- Prices (chain, reworked 2026-07 — see quirks ledger): incremental = BR
  archiwum notowań page 1 (robots-allowed, ~50 sessions) → Yahoo v8 chart →
  BR profile quote; backfill = Yahoo (5y) → stooq (one chance; it denies
  non-browser clients) → BR archiwum → profile quote.

API: `POST /api/companies/{ticker}/refresh?scope=financials|prices|all&force=` · `GET /api/companies/{ticker}/financials?statement=&freq=` · `/indicators` · `/dividends` · `/prices`

## 7. Module C — Aggregation & presentation

### Metrics engine (`services/metrics.py`, pure functions)

Per quarter, computed from `report_values`:
- revenue r/r dynamics; gross sales margin **(marża brutto na sprzedaży — his key metric)**; sales margin after SG&A; net margin
- operating leverage flag (profit growing faster than revenue)
- one-off share: pozostała działalność operacyjna / operating profit (heuristic for one-off distortion)
- TTM: net profit, EPS; market cap & C/Z TTM from latest price + shares
- C/Z vs own history: median + quartiles of company's historical C/Z (from indicators), current & forward position vs that range
- net cash/debt from balance sheet; dividend continuity

### Deterministic prescore

Rule-based pass/fail/unknown per checklist item, each with the numbers as evidence (feeds both UI and the AI prompt): revenue growth, margin trend, operating leverage, profit quality (one-offs), C/Z vs own history, net cash, small-cap, dividend bonus. Cheap, instant, no API cost — AI covers only what rules can't (catalysts, thesis, management credibility, forum insight).

### Forecast engine (`services/forecast.py`)

Replicates the Excel transcript workflow. Inputs (all prefilled with defaults, all overridable):

| Assumption | Default |
|---|---|
| Przychody | last quarter (UI shows y/y seasonality hint) |
| Marża brutto na sprzedaży % | last quarter |
| Koszty sprzedaży | avg % of revenue, last 4 q |
| Koszty ogólnego zarządu | last quarter (+ hint: Q4 reserve bump pattern) |
| Pozostała działalność operacyjna | avg last 4 q |
| Działalność finansowa | avg last 4 q (manual override for FX-sensitive companies) |
| Podatek | 19 % |
| Amortyzacja (dla EBITDA) | last quarter |

Output: forecast P&L line by line → net profit, EPS, EBITDA; forecast quarter vs same quarter y/y; TTM including forecast → **forward C/Z at current price**. Scenarios saved per company.

### Frontend (Next.js + SCSS, UI in Polish)

Approved designs live in `docs/design/` — `mockups.html` (both screens, final dark palette) and `design.md` (SCSS tokens + component rules). Phase 4 implements these, not a new design.

- `/` — watchlist: ticker, kurs, mcap, C/Z TTM, forward C/Z (latest forecast), marża trend, dynamika przychodów r/r, last AI score, data freshness; add/remove ticker
- `/spolka/[ticker]` — tabs:
  - **Przegląd** — key numbers, prescore checklist with evidence, price chart
  - **Finanse** — statement tables Q/Y (BiznesRadar layout familiar to you)
  - **Wykresy** — the Excel "Wykresy" sheet as interactive charts: przychody, marża brutto, zysk ze sprzedaży, zysk netto — q/q sequence and y/y quarter comparison
  - **Prognoza** — forecast editor (defaults prefilled, live recompute, save scenario, forward C/Z result)
  - **Forum** — linked topics, post timeline, author filter
  - **Analiza AI** — run analysis, verdict history
- `/ustawienia` — connection status (PA login OK?, Anthropic key present?, DB OK) — status only, values never leave backend

## 8. Module D — Strategy skill & AI analysis

### The skill (`skill/`)

`SKILL.md` distills the four source documents into analyst instructions: philosophy (stock picking, thesis-first), the 14-point OBS checklist, the 7 golden rules, catalyst taxonomy, one-off vs sustainable improvement guidance, red flags (management credibility, related-party transactions), valuation approach (forward C/Z vs own history, margin of safety). `rubric.md` defines per-item weights → alignment score 0–100. `examples/` holds 2–3 worked examples distilled from real OBS reasoning in `obs.txt` (few-shot grounding).

Kept as plain markdown so it's versionable, editable by you, and reusable as a Cowork skill outside the app.

### Forum distillation (before the analysis run)

Forum posts are **unverified opinions** — never fed to the verdict as facts.
A separate distillation pass (cheap model, batched) classifies each post
(fact-claim / opinion / question / noise), extracts concrete claims with a
confidence level and source post ids, and caches results per post — so each
post is analyzed once, ever. Upvotes (stored per post) weight which posts get
distilled first within the token budget. Crucially this runs over posts
already synced into the DB — it triggers **zero** additional forum requests,
so rate limits are untouched. The verdict prompt then receives distilled
claims labeled with confidence, not raw posts.

### Analysis run (`analysis/`)

1. Build input: dossier JSON (metrics, prescore, last 8 quarters of key lines, C/Z history stats, dividends) + recent forum posts (newest first, token-capped ~30k; full-thread summarization = extension) 
2. Call Claude API — system prompt = SKILL.md + rubric; forced structured output (tool use JSON schema)
3. Persist to `analyses`, render in UI

Output schema: `thesis` (or "no thesis found"), `catalysts[]` (type, description, horizon, priced-in?), `checklist[]` (item, verdict, evidence), `red_flags[]`, `one_off_risk`, `forum_insights`, `alignment_score` 0–100, `potential` (upside/downside case), `verify_next[]` (what to check after next report), `summary_pl`.

Model default `claude-sonnet-4-6`, configurable (`ANTHROPIC_MODEL`). Token counts logged per run. Each analysis stores its input snapshot → re-run after next quarterly report and diff verdicts = the "thesis verification" loop from the strategy.

## 9. Config & secrets

Local: `backend/.env` + `frontend/.env.local` (both gitignored, `.example` files committed). Production: the same variables set in Railway / Vercel dashboards — never in the repo.

- Backend (local `.env` / Railway): `DATABASE_URL`, `PA_USERNAME`, `PA_PASSWORD`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `API_TOKEN` (shared bearer, prod only), `AI_DAILY_LIMIT`
- Frontend (local `.env.local` / Vercel): `BACKEND_URL`, `BACKEND_API_TOKEN` (server-side only), `AUTH_SECRET`, `AUTH_GOOGLE_ID`, `AUTH_GOOGLE_SECRET`, `ALLOWED_EMAILS`

Loaded via pydantic-settings (backend); secrets never reach the browser or DB.

## 9a. Production topology & auth

```
Browser ──► Vercel: Next.js + Auth.js (Google sign-in, ALLOWED_EMAILS allowlist)
                │  route-handler proxy /api/* → adds Bearer API_TOKEN + X-User-Email
                ▼
            Railway: FastAPI container ──► Railway Postgres
                │  polite scrapers + Claude API
                ▼
            biznesradar.pl · portalanaliz.pl · yahoo/stooq · api.anthropic.com
```

- The browser never calls Railway directly: all frontend API calls go through Next.js route handlers (`app/api/[...path]`) that check the Auth.js session, then forward server-to-server with a static bearer token. Backend middleware rejects requests without the token. No CORS, one trust boundary, ~50 lines total.
- `X-User-Email` is passed through so analyses/forecasts record who ran them.
- Local dev: no auth (middleware activates only when `API_TOKEN` is set), proxy points at `localhost:8000` — same code path in dev and prod.
- Cost guard: `AI_DAILY_LIMIT` caps Claude analyses per day globally, protecting your API bill from enthusiastic friends.

## 10. Build order, phases, extension points

Phases match your four dividable parts; B before A only because everything downstream feeds on financials. A and B are independent — order can swap.

| Phase | Scope | Done when |
|---|---|---|
| 0 | Scaffold: repo layout, docker-compose (postgres), FastAPI skeleton + `/api/health`, Next.js + SCSS skeleton, `.env.example`, README | both apps run, DB migration applies |
| 1 | **Module B** — BiznesRadar + stooq scrapers | `refresh` fills DB for a real ticker; parsers green against fixtures |
| 2 | **Module A** — PortalAnaliz scraper | link topic → full sync → incremental sync works on a real thread |
| 3 | **Module C (backend)** — metrics, prescore, forecast, dossier | dossier endpoint returns correct numbers verified against BiznesRadar by hand |
| 4 | **Module C (frontend)** — watchlist + stock page tabs | you can do your full manual workflow in the app instead of Excel |
| 5 | **Module D** — skill + Claude integration + Analiza tab | end-to-end analysis of a watchlist stock produces a structured, sensible verdict |
| 6 | Deploy & polish — Railway (backend+DB) + Vercel (frontend), Auth.js Google allowlist, proxy + bearer token, backups | app live; you and allowlisted friends sign in with Google; everyone else gets a login wall |

Explicit **extension points** (documented, not built). Each was checked against the current architecture — none requires restructuring:

- **Market-wide screener** over prescore; **forum topic auto-discovery**; **US stocks** via stockanalysis.com.
- **BiznesRadar premium login** (task P1.9, user has an account): optional `BR_USERNAME/BR_PASSWORD`, session login before page fetches → longer statement/indicator history (better own-history C/Z stats). Fits cleanly: scrapers already accept a shared `requests.Session`; needs one recorded login-page fixture to implement the form flow.
- **ESPI/EBI feed + e-mail alerts** (espiebi.pap.pl / stockwatch.pl): new `scrapers/espi.py` (fetch+parse+upsert into a new `espi_reports` table keyed by report id), polled for watchlist tickers by the scheduler extension (Railway cron → internal endpoint); a notifier module e-mails you when the distiller flags a report as material for an observed stock. Fits: same polite-fetch path, same long-format storage, analyses layer already consumes per-company events.
- **"Hotness" score with self-learning backtests** (0–100 potential): the DB already stores everything a backtest needs — dated forum posts (+upvotes), financials per quarter, daily prices for outcome labels, and AI verdicts with input snapshots. A later `research/` module can replay history (posts+financials known at time T → price outcome at T+n) to calibrate weights without any schema change. Complex; explicitly parked until the base runs in production.

## 11. Testing (pragmatic)

- Parsers: pytest against recorded HTML fixtures — the one place regressions are likely (site markup changes).
- Metrics/forecast: unit tests with hand-checked numbers (e.g. Novita example from the transcript).
- API: a few happy-path tests via FastAPI TestClient.
- Frontend: no test suite in v1; manual verification. (Extension: Playwright smoke test.)

## 12. Risks & etiquette

- **Site markup changes** → parsers isolated per page type + fixtures make fixes quick and verifiable.
- **Anti-bot blocking** → all scraper traffic goes through one shared fetch helper (`scrapers/http.py`): per-domain rate limit with **randomized jitter** (BR ~2–4 s, PA ~1.5–3 s), realistic browser UA, exponential backoff on 403/429/5xx with a hard stop after repeated failures, sequential fetches only, 24 h cache so pages are never refetched needlessly. Low volume by design (watchlist-scale, ~7 pages per company). Screener postponed partly for this reason.
- **Datacenter IP** → Railway egress IPs are cloud IPs, which some sites treat less kindly than home connections. Mitigated by the same politeness rules; if BiznesRadar ever blocks, fallback documented in extension backlog (run scrapes from a home machine or tiny VPS that pushes to the same DB).
- **Terms of use** → personal small-circle tool; data stays in your DB; no public exposure or redistribution (forum content is behind your PA account — keep the circle private). PA scraping only with your own account.
- **AI cost** → prescore is free; AI runs are manual (button), token-capped, logged, and capped per day (`AI_DAILY_LIMIT`) since friends share your API key.
- **Not investment advice** → the app supports your process; verdicts are inputs to your judgment, as OBS himself insists ("odradzam naśladownictwo").

## 13. Learning layer

The project doubles as learning material (mid C# dev → Python + frontend). Kept strictly additive — it never changes what gets built:

- `docs/learning/00-stack-for-csharp-devs.md` — mapping of every stack piece to its .NET counterpart (FastAPI ≈ minimal APIs, SQLAlchemy ≈ EF Core, Alembic ≈ EF migrations, …). Read before Phase 0.
- After each phase: `docs/learning/phase-N.md`, max one page — what was built, the 3–5 web-dev concepts it introduced, C# analogies, what to look at in the code.
- Code style follows from this: idiomatic and readable over clever; non-obvious choices get a one-line comment saying *why*, not what.
- During implementation sessions, ask "why" about anything — explanations on demand instead of tutorial bloat in the repo.
