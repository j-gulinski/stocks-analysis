# Changelog archive — 2026-07-07 (build day, full detail)

Full text of the twelve same-day entries from the project's build day,
moved out of the always-loaded `CHANGELOG.md` during the 2026-07-07 memory
consolidation. The durable technical findings live in
`skills/scraper-doctor/SKILL.md` (quirks ledger); this file preserves the
narrative and decisions verbatim.

---

## 2026-07-07 · Verification round: indicators, price history, technical statuses

User verified data completeness after the slug fix — three gaps closed:

- **Mediana C/Z was empty because live indicator labels are long-form**
  ("Cena / Zysk", not "C/Z") and label normalization kept spaces around the
  slash. Slashes are now tightened in `normalize_label`; long forms map
  (cz/cwk/cp), Grahama & zysk-operacyjny cousins stay deliberately unmapped.
  Verified against the live wskazniki page (headers `2025/Q1 (gru 24)` parse).
- **Price chain reordered: Yahoo → stooq → BR profile quote** (user verdict:
  stooq CSV is dead for non-browser clients — kept only as a cheap second
  chance). **History backfill:** a lone fallback-quote row used to set
  last_day=today and block history forever; with < MIN_PRICE_HISTORY_ROWS
  (30) stored rows the fetch now pulls the full range and REPLACES the stubs.
- **Technical refresh statuses (user request):** every report entry now shows
  shape + range ("ok (612 values; 27 rows × 24 periods; 2016Q3–2026Q2)"),
  prices show day-count/range/source, up-to-date shows stored history size;
  the stock-page panel renders them as a monospace checklist.
- Stopa dywidendy card: newest year can be declared-but-unpaid — UI now shows
  the latest dividend with a real yield.

## 2026-07-07 · The redirect discovery — live BR page finally inspected

web_fetch succeeded against the live SNT page; every remaining mystery fell:

- **Root cause of all "annual data as quarters":** BR redirects ticker URLs
  to the company-name slug and DROPS the `,Q` suffix (`/SNT,Q` →
  `/SYNEKTIK`). Fix: `companies.br_slug` (migration 0003) resolved from the
  profile page; all report URLs now use the slug. Profile fetch overrides the
  cache when the slug is unknown.
- **Phantom quarters explained:** the header-scan once picked the "Data
  publikacji" row — its publication dates (2010-02-14…) became 2010Q1-style
  periods. That row is now excluded from header detection.
- **Annual headers** (`2018 (paź 18)`) parse correctly; the trailing
  `O4K (mar 26)*` TTM column is skipped.
- **Real income data-field codes** applied; the big trap: `IncomeGrossProfit`
  = "Zysk ze sprzedaży" = profit AFTER SG&A → remapped to `profit_on_sales`;
  true gross stays derived (revenue − IncomeCostOfSales).
- Profile: name no longer crosses `:` in titles; sector read from the
  `Branża:` label cell (DOM-first); market from the "GPW - Akcje" banner.
- **Prices:** skip providers entirely when the DB already has today's close
  (production sent future `d1=` and inverted Yahoo period1>period2 → 429);
  Yahoo URL clamps defensively.
- **stooq verdict (user question):** CSV endpoints return 404/denials for
  non-browser clients from multiple networks (verified via sandbox fetches +
  user's browser "access denied"). Kept as first-chance attempt (cheap, may
  recover), but the effective chain is Yahoo (now with fixed params) + BR
  profile quote; stooq-with-login remains a documented extension.

## 2026-07-07 · Prices chain + replace-on-force (UniqueViolation round 2)

- **Confirmed from production log: `,Q` works** — CBF now returns the true
  quarterly grid (2016Q3: 20 149 → 2016Q4: 22 714 → …).
- **Crash root cause:** earlier runs left mislabeled rows (annual data stored
  as quarters); plain upserts never purge, and inserts could still collide.
  Fixes: (1) forced refresh = **replace semantics** (DELETE the statement's
  rows, then insert — stale phantom periods are purged), (2) writes use
  native `INSERT … ON CONFLICT DO UPDATE` (PG + SQLite) after in-memory
  dedup — UniqueViolation is impossible by construction, (3) commit guarded:
  IntegrityError → rollback + `database: error: …` in the summary, never a 500.
- **Yahoo Finance added as second price source** (`SNT.WA`, v8 chart JSON):
  chain is stooq → Yahoo → BR profile quote. Initial pull lightened to 5y
  (Yahoo 429s aggressive first requests — observed in production).
- **Kalkulacyjny layout support (SNT):** BR tags its 'Zysk ze sprzedaży' row
  as IncomeGrossProfit and has no profit-on-sales row — `cogs` canonical
  added and `derive_income_fields` computes gross profit (revenue − cogs)
  and profit-on-sales (gross − SG&A) when absent. Fills the empty 'Zysk ze
  sprzedaży' chart.
- **Condensed-grid warning:** quarterly tables that look like one-column-per-
  year get flagged in the summary ("kolumny wyglądają na roczne") — the
  'data not fully queried' symptom is now self-diagnosing.

## 2026-07-07 · CBF crash round — the `,Q` discovery + fetch-volume guards

The CBF traceback (UniqueViolation on income,Y,2026) solved the whole
"0 values" mystery:

- **Root cause found: bare BiznesRadar statement URLs serve the ANNUAL view
  for some companies.** CBF's "quarterly" data was actually fiscal-year
  columns; SNT's income page parsed zero columns. Quarterly is now requested
  explicitly (`…/{TICKER},Q`) — never trust the default view.
- **Crash fixed:** annual pages can repeat a period column (`2026` twice) —
  parser keeps the first occurrence AND the upsert dedupes within a batch
  (it only checked against the DB before).
- **Header-row scan:** the period header is not always the first `<tr>`;
  the parser now scans the first 5 rows and picks the best match. Periods
  also accept report dates (`2025-03-31` → `2025Q1`).
- **stooq "Access denied" arrives as HTTP 200 with the message in the body**
  (user saw it in the browser too): detected now, stops after ONE request
  (`StooqLimitError`) instead of hammering 4 URLs.
- **Price of last resort:** the profile page's quote (`meta itemprop=price` /
  `Kurs:` text) becomes today's close when stooq fails — zero extra requests.
- **Fetch-volume transparency (user concern):** every refresh summary now
  ends with `requests: ok (n HTTP)`. Full forced refresh ≈ ≤12 requests
  over ~30–45 s; cached ≈ 0–1; forum sync ~1 page per 50 new posts.
- **"Data publikacji" metadata rows** are no longer stored as values.
- **New skill (user idea): `skills/scraper-doctor/SKILL.md`** — diagnostic
  ladder + verified quirks ledger so future sessions never re-derive today's
  findings; wired into CLAUDE.md. Plus `scripts/record_topic_fixture.py`.
- Validated from the traceback: income `data-field` codes (IncomeRevenues…)
  and labels ("Przychody ze sprzedaży") match existing aliases — income
  metrics light up once `,Q` pages land.

## 2026-07-07 · SNT mapping-report round — balance mapped by code, profile round 2

- **Balance sheet now matched by BiznesRadar `data-field` codes** (real
  vocabulary from the user's mapping-report): labels duplicate between the
  long/short sections ("Kredyty i pożyczki" twice), so codes are the primary
  key; ambiguous bare labels stay honestly unmapped.
- **Net debt is granular:** borrowings + bonds (dłużne papiery) + leasing,
  long and short — `compute_net_cash` sums every `debt_*` component present
  and says how many it used.
- **Profile round 2:** 'Notowania SYNEKTIK SA (SNT)' no longer leaks the
  "Notowania" prefix into the name; market label requires a colon
  ("Rynek: …") so menu links ("Rynek NewConnect") can't mislabel companies.
- **Diagnosis from the report:** income/cashflow/indicators_value stored
  0 values while indicators_profitability stored 320 → those pages use a
  different period-header format (likely dates). Blocked on real HTML:
  waiting for `scripts/record_fixtures.py SNT` output (lands in
  tests/fixtures/real_*, structural tests pick them up automatically).

## 2026-07-07 · Prices fix round (SNT: "stooq returned HTTP 404")

- **stooq resilience:** history CSV tried on stooq.pl then stooq.com; if both
  fail, the current-quote endpoint (`/q/l/`) supplies today's close — kurs,
  mcap and C/Z TTM work even without history (chart degrades gracefully).
  Errors now list every attempted URL in the refresh summary.
- **Forced refresh from UI:** the stock-page button bypasses the 24 h cache
  (the user force-refreshed and saw everything "cached"); watchlist bulk
  refresh keeps using the cache by design.
- `_SPACE_CHARS` rewritten as `\uXXXX` escapes — invisible unicode spaces are
  editor-"cleanup" bait.
- Awaiting user's `mapping-report` JSON to extend income-statement aliases —
  the remaining cause of "b/d" metrics.

## 2026-07-07 · Production feedback round (SNT test) — fixes + plan growth

Field-reported by the user after running the app on real data:

- **Fixed: watchlist DELETE 500** — proxy built a 204 response with a body,
  which `Response()` rejects; null-body statuses now pass through bodyless.
- **Fixed: company name "Notowania SNT"** — BR's `<h1>` is a generic listing
  header; name now parsed from `NAME (TICKER)` across title/h1/h2, generic
  headers never stored. Market label only from explicit "Rynek:" (nav menus
  mention NewConnect everywhere and mislabeled main-market SNT).
- **Fixed: one bad page blanked whole refresh** — `UnknownTickerError` now
  raised only when *every* page failed and no data exists.
- **Diagnostics (new):** `GET /api/health/scrapers` (per-source last success /
  errors 24 h, shown in Settings) and `GET /api/companies/{t}/mapping-report`
  (statement rows the field mapper doesn't recognize — the "why b/d?" tool);
  refresh summary now rendered on the stock page, error hint on the watchlist.
- **Forum upvotes:** `forum_posts.upvotes` (migration 0002), best-effort
  parser (selector list, needs verification against a recorded real page),
  `sort=top` + UI toggle — groundwork for AI token budgeting.
- **UX:** rotating loading messages + skeletons (Claude-style visible
  progress), larger touch targets (36 px controls), refresh shows staged
  status messages.
- **README:** direct `.env` content to create (user disliked copy-from-example),
  troubleshooting section.
- **Planned (PLAN §10, TASKS):** P1.9 BiznesRadar premium login (user has an
  account — longer histories); P5.9 forum distiller (posts as unverified
  claims with confidence, cached per post, zero extra fetches); extensions:
  ESPI/EBI poller + e-mail alerts, self-learning hotness score via backtests
  (architecture-fit checked: no schema changes needed — parked until the base
  is stable in production).

## 2026-07-07 · P0.5 + P4 · Frontend (Next.js 15 + SCSS, dark theme)

- Skeleton: App Router + TS, SCSS design system from `docs/design/design.md`
  as global primitives (`.card`, `.btn`, `.badge`, `.table`, `.tabs`, tokens),
  route-handler proxy `app/api/[...path]` → `BACKEND_URL` (Phase-6-ready:
  bearer token + X-User-Email attach point), typed API client + DTO mirror.
- Watchlist `/`: dossier-driven table (kurs, mcap, C/Z TTM/fwd, marża trend,
  przych. r/r, freshness), add/remove, per-row refresh, sequential refresh-all.
- Stock page `/stock/[ticker]`: Overview (metric cards, prescore checklist,
  price chart), Financials (Q/Y statements, sticky label column), Charts
  (4 quarterly charts, sequence + y/y views), Forecast (prefilled assumptions,
  debounced live recompute via `save=false`, scenario save/load), Forum
  (link topic, sync, author filter, pagination). AI tab disabled until Phase 5.
- `/settings`: backend/DB + PA login status checks.
- **Decision (user):** navigation and tab labels in English; domain data and
  evidence stay Polish. Route renamed `/spolka` → `/stock`.
- **Decision:** global SCSS primitives instead of per-component modules —
  fewer files, one design source; revisit only if styles start colliding.
- **Verification:** npm registry unavailable in sandbox — configs JSON-checked,
  "use client" placement, local-import resolution, brace balance and API-usage
  cross-check all pass statically. Run `npm install && npm run dev` locally.

## 2026-07-07 · P3 · Analytics core (metrics, prescore, forecast, dossier)

- `services/metrics.py`: quarterly metrics (rev y/y, gross/sales/net margin,
  one-off share), TTM (net, EPS, C/Z, mcap), own-history P/E stats, net cash,
  8-rule deterministic prescore with pass/fail/**unknown** + evidence.
- `services/forecast.py`: Excel-workflow forecast (defaults from history,
  full P&L, y/y, forward C/Z); verified against the Novita transcript shape.
- `services/dossier.py` + endpoints: `GET /companies/{t}` (dossier),
  `GET /forecast-defaults`, `POST/GET /forecasts` (preview via `save=false`);
  saved forecasts switch the valuation check to forward P/E.
- Changelog discipline added: this file + `.githooks/pre-commit` + CLAUDE.md rule.
- Learning notes `docs/learning/phase-0..3.md`; root README with run/test steps.
- **Units decision:** statements in tys. PLN, price PLN, mcap PLN;
  `eps = ttm × 1000 / shares` in exactly one place.
- **Verification note:** sandbox lost PyPI mid-session, so FastAPI/SQLAlchemy
  layers are covered by the committed pytest suite (run locally: `cd backend &&
  pytest`); parsers, metrics and forecast math were additionally executed
  directly against fixtures with hand-checked numbers — all green.

## 2026-07-07 · P1–P2 · Backend scrapers (BiznesRadar, stooq, PortalAnaliz)

- `scrapers/http.py`: single polite fetch path — per-domain jittered delays
  (BR 2–4 s, PA 1.5–3 s), realistic UA, backoff ×3 then `FetchBlockedError`.
- `scrapers/biznesradar.py`: one generic `report-table` parser reused by all
  statement/indicator pages + profile & dividend parsers.
- `scrapers/stooq.py`: daily prices via CSV download (PL/EN headers).
- `scrapers/portalanaliz.py`: phpBB login, topic-page parser, URL canonicalizer
  (markup per verified reference scraper).
- `services/refresh.py`: orchestration, 24 h fetch-cache via `fetch_log`,
  per-page error isolation, idempotent upserts, incremental price loading.
- `services/forum_sync.py`: topic linking + incremental sync from last partial
  page; deleted-post offset drift accepted as v1 limitation (see PLAN §10).
- API: watchlist CRUD, refresh, financials/indicators/dividends/prices reads,
  forum link/sync/read, login-status.
- **Decision:** committed fixtures are synthetic (sandbox had no access to BR);
  `scripts/record_fixtures.py` records real pages as `real_*` fixtures which
  activate additional structural tests (P1.1 remains open until run).
- **Decision:** `field_code` falls back to a label slug when BiznesRadar has no
  `data-field`; canonical meaning is assigned only in `services/fields.py`.

## 2026-07-07 · P0 · Backend scaffold

- Monorepo layout per PLAN §2; source docs moved to `docs/source-materials/`.
- FastAPI app factory + `/api/health`; typed SQLAlchemy 2.0 models for the full
  PLAN §4 schema (incl. Phase-5 `analyses` to keep migrations linear);
  hand-written Alembic `0001_initial`; docker-compose Postgres 16.
- **Decision:** client-side UTC timestamps (not DB `now()`) so the identical
  schema runs on SQLite in tests and PostgreSQL in production.
- **Decision:** added `report_values.position` so statement tables render in
  original BiznesRadar row order.
- P0.5 (frontend skeleton) deferred to the frontend session.

## 2026-07-07 · Planning · PLAN, TASKS, designs, deployment, learning layer

- PLAN.md (architecture, 4 modules A–D, phases) + TASKS.md (49 tasks, stable
  IDs) + CLAUDE.md distilled from the four Malik/OBS source documents.
- UI designs approved and saved: `docs/design/mockups.html` + `design.md`
  (dark palette, Polish UI).
- **Decision:** PostgreSQL over SQLite (user choice); watchlist-first, screener
  postponed; Claude API for the analysis layer.
- **Decision:** production = Vercel (frontend) + Railway (backend+Postgres);
  Auth.js Google allowlist; browser→backend only via Next proxy with static
  bearer token; `AI_DAILY_LIMIT` cost guard.
- Learning layer added (docs/learning/, C# analogies; PLAN §13).
