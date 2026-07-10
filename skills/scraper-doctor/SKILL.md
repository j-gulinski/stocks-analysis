---
name: scraper-doctor
description: Systematic protocol for diagnosing and fixing scraper/data problems in the Stock Analysis Workbench (BiznesRadar, Yahoo, stooq, PortalAnaliz). Use whenever refresh shows errors, metrics show "b/d", values look wrong, or a site changed its markup.
---

# Scraper doctor

Protocol for web-page/data problems in this project. Follow the ladder in
order — every step narrows the cause without new guesses. Politeness rules
are NON-NEGOTIABLE at every step (see bottom).

## Diagnostic ladder

1. **Read the refresh summary** (stock page badge strip, or the `summary`
   JSON from `POST /api/companies/{t}/refresh?force=true`). Each page reports
   `ok (n values)` / `cached` / `error: …`. `ok (0 values)` = parsed but no
   period columns recognized (header-format problem, not fetch problem).
   Indicator pages list dropped rows: `pominięte: <labels>` — an unmapped
   indicator is visible here, not silent.
2. **`GET /api/health/scrapers`** — per-source last success / last error /
   errors 24 h (biznesradar, stooq, yahoo, portalanaliz). Distinguishes
   "site blocks us" from "we parse it wrong".
3. **`GET /api/companies/{t}/mapping-report`** — every stored statement row
   with its canonical mapping (`canonical: null` = extend
   `backend/app/services/fields.py`; raw rows are stored, no re-scrape
   needed) + `indicators_stored` / `indicators_never_seen`.
4. **Record real pages**: `python scripts/record_fixtures.py TICKER` (and
   `python scripts/record_topic_fixture.py TOPIC_URL` for the forum). Files
   land in `backend/tests/fixtures/real_*`; structural tests pick them up
   automatically (`pytest tests/test_biznesradar_parser.py -v`).
5. **Fix in exactly one place**: markup → `app/scrapers/*.py`; meaning →
   `app/services/fields.py`. Never both blindly, never anywhere else.
6. **Every fix ships with a test** reproducing the production shape, and a
   CHANGELOG entry describing symptom → cause → fix.

## Quirks ledger (verified in production — do not re-learn)

### BiznesRadar — URLs & robots
- **THE redirect trap (root cause of most 'wrong data' bugs):** ticker URLs
  redirect to the company-name slug (`/…/SNT,Q` → `/…/SYNEKTIK`) and the
  redirect **DROPS the ,Q/,Y suffix**, silently serving the annual view.
  Report pages MUST be fetched by slug (`companies.br_slug`, resolved from
  the profile page's `/notowania/{SLUG}` link). Quarterly = `{SLUG},Q`,
  annual = `,Y`, cumulative = `,C`.
- **robots.txt (checked 2026-07):** `Allow: /` with `Disallow` only for
  `/transakcje/*,*`, `/profile-*/*,*` and `/notowania-historyczne/*,*` —
  i.e. the archiwum-notowań FIRST page is allowed, its `,2`,`,3`…
  pagination is NOT. The app therefore fetches archiwum **page 1 only**
  (~50 sessions). Never paginate it.

### BiznesRadar — report tables
- **Period headers come in mixed formats per page/company**: `2025/Q1`,
  report dates `2025-03-31` (month→quarter), bare years, annual
  `2018 (paź 18)`. The parser scans the first 5 table rows and picks the row
  with the most period-like cells — the header is NOT always the first
  `<tr>`. The trailing `O4K (mar 26)*` TTM column must be skipped.
- The `Data publikacji` row is metadata (dates would become phantom periods
  like 2010Q1) — excluded from header detection AND from stored values
  (`IGNORED_ROW_LABELS`).
- **Annual pages can repeat a period column** (`2026` twice) — parser keeps
  the FIRST occurrence; upserts also dedupe in-batch (crashed prod once).
- **`data-field` codes are the stable row identity** (`IncomeRevenues`,
  `BalanceCash`, `CZ`, `CWK`…). Labels DUPLICATE between sections
  ("Kredyty i pożyczki" in long- and short-term) — match codes first,
  labels only when unambiguous.
- **Code trap:** `IncomeGrossProfit` is BR's code for "Zysk ze sprzedaży" —
  profit AFTER SG&A (`profit_on_sales`), NOT gross profit. True gross is
  derived: revenue − cogs (kalkulacyjny) or pos + selling + admin (reverse).
- A quarterly table whose periods are ~1-per-year is a condensed/annual view
  in disguise — the summary flags it ("kolumny wyglądają na roczne").
- **Financial debt is granular**: borrowings + bonds + leasing × long/short.
  Net cash sums every `debt_*` component present.

### BiznesRadar — profile page
- `<h1>` is a generic "Notowania {TICKER}" — company name comes from a
  `NAME (TICKER)` pattern in title/h1/h2, minus prefix words. Menu links
  mention "Rynek NewConnect" on every page — only an explicit `Rynek: X`
  label or the "GPW - Akcje" banner identifies the market.
- Sidebar labels: `Branża:` (not `Sektor:`); shares under `Liczba akcji:`.
  **Free-float trap:** "Liczba akcji w wolnym obrocie" appears near "Liczba
  akcji" — the shares regex must require `:` + digits immediately, or the
  smaller free-float count gets captured (this understated market cap and
  made a >1 mld PLN company score "small" in production).
- **`Kapitalizacja:` and `Enterprise Value:` are in the info box** — live
  page shows full integers ("2 821 435 788"); parse defensively for scaled
  "2,82 mld" too. **The REPORTED mcap is authoritative** for size
  classification (stored on `companies.market_cap`); price × shares is only
  a fallback and its deviation is surfaced (`market_cap_check_pct`).
- Profile carries the current quote (`<meta itemprop="price">`, or `Kurs: …`
  text) — the price source of last resort, zero extra requests.
- Anonymous pages can be served from a stale CDN cache (quote minutes old,
  archiwum sometimes weeks behind the profile) — treat freshness per page,
  surface `price_age_days`, never assume "just fetched = today".

### BiznesRadar — indicator pages
- Long labels with spaced slashes: "Cena / Zysk", "Cena / Wartość księgowa",
  "Cena / Przychody ze sprzedaży", "Cena / Zysk operacyjny" — normalization
  tightens "/" before matching. Headers like `2025/Q1 (gru 24)` parse.
- Cousins that must NEVER map to cz/cwk/gross_margin: "Cena / Wartość
  księgowa Grahama", and **"Marża zysku brutto" (PRETAX margin — not the
  gross-sales margin!)**. "Cena / Zysk operacyjny" maps to its OWN code
  `czo`.
- Matching is code-first (`<tr data-field="CZ">`) with exact-label fallback;
  when a guessed code and a live-verified label disagree, the label wins.
  Dropped labels are listed in the refresh summary (`pominięte: …`).

### BiznesRadar — premium login (VERIFIED 2026-07-08, live browser capture)
- **There is NO server-rendered login page.** `/logowanie` and `/login` (no
  trailing slash) both return HTTP 404. The header "Logowanie" link is
  `<a href="javascript:void(0)" onclick="Dialogs.login()">` — the form is built
  client-side in a JS modal and never appears in static HTML. Do NOT scrape a
  login form or probe `/logowanie`.
- **Fixed endpoint:** `POST https://www.biznesradar.pl/login/` (TRAILING SLASH
  required), form-encoded `email` + `password` (+ optional `remember_me=1`).
  NO CSRF token, no hidden inputs — nothing to echo back.
- **Redirect on both success AND failure** (opaqueredirect to a browser
  fetch): the POST body is not authoritative. Follow the redirect, then
  re-fetch the homepage and check a marker.
- **Logged-in marker:** the homepage HTML contains `account-settings`
  (`Dialogs.accountSettings`); the anonymous page carries `Dialogs.login`
  instead and lacks `account-settings`. Secondary marker: `GET /user-data/`
  returns ~194 B anonymous vs ~1686 B logged in (length > 1000 ⇒ logged in).
- **There is NO logout href** (`/logout`, `/wyloguj` absent — logout is JS
  too). Never key success off a logout link or off a login form being absent.
- `BR_USERNAME` is the account **e-mail** (email-shaped, verified). Recipe
  lives in `BrClient.login()` (warm-up GET → POST /login/ {email, password} →
  verify marker); `services/refresh.py` threads the session into every BR
  fetch and a login failure is non-fatal (refresh continues anonymously).
  Fixture: `tests/fixtures/br_login_live.html` (exact captured modal form).

### Price chain (reworked 2026-07 after both CSV providers broke)
- **Incremental (daily top-up): BR archiwum page 1 → Yahoo → BR profile
  quote.** stooq is deliberately SKIPPED — it answers "access denied" to
  non-browser clients; hitting it daily after that signal is impolite.
- **Backfill (<30 stored rows): Yahoo (5y in one request) → stooq (its one
  chance) → BR archiwum page 1 (~50 sessions) → BR profile quote.**
- Archiwum table: `Data | Otwarcie | Max | Min | Zamknięcie | Wolumen |
  Obrót`, dates dd.mm.yyyy, newest first — parser finds it by header labels,
  returns bars oldest→newest.
- A lone fallback-quote row must never block history: below 30 stored rows
  the fetch pulls the full range and REPLACES the stubs.
- **Future-dated price rows froze the chain forever** (`last_day >= today`
  guard → "aktualne" every day) — they are purged on every refresh and
  never re-stored (`bar.day > today` is skipped).
- Never request prices when today's close is already stored.

### stooq
- History CSV `/q/d/l/?s={t}&i=d`, quote CSV `/q/l/?s=…&e=csv`; `.pl` and
  `.com` mirrors. Can 404 ALL endpoints (IP/UA-level) — verified from
  multiple networks + user's own browser.
- **Daily-limit / "Access denied" arrives as HTTP 200 with the message in
  the body** — detected (`StooqLimitError`), stops after ONE request.
  Retrying other endpoints is pointless and rude. Limit resets daily.
- stooq-with-login remains a documented extension, not implemented.

### Yahoo Finance
- v8 chart JSON, symbol `{TICKER}.WA`; hosts query1 AND query2 (one edge
  sometimes rejects what the other accepts). Browser-ish headers (Accept,
  Accept-Language, Referer) noticeably improve acceptance; a full
  cookie+crumb handshake is out of scope — Yahoo is best-effort only.
- Initial range 5y (10y pulls got 429). Clamp `period1 < period2` — a future
  start once produced inverted ranges and 429s. On `FetchBlockedError` from
  host 1 do NOT try host 2 (both are rate-limited; respect the signal).

### Storage rules (learned from two UniqueViolation crashes)
- Forced refresh uses REPLACE semantics per statement (delete then insert) —
  stale/mislabeled periods must be purged; plain upserts can't.
- All report-value writes go through `INSERT … ON CONFLICT DO UPDATE` with
  in-memory dedup first — never ORM add() loops for scraped series.
- Group vs parent-shareholders rows: when several rows map to one canonical
  field, the highest-ranked wins (parent "akcjonariuszy jednostki
  dominującej" > data-field code > plain alias) — deterministic across
  layouts; EPS/P-E comparability depends on it.

### PortalAnaliz (phpBB)
- Posts: `div.post` with id `p{post_id}`; author `a.username(-coloured)`;
  `time[datetime]`; body `div.content`. Pagination via `start`, 50/page.
- Login needs the form's hidden anti-CSRF fields AND a ~2 s pause before the
  POST (form-token minimum age).
- Topic pages can return the login page with HTTP 200 to an anonymous client;
  `record_topic_fixture.py` must authenticate through `ForumClient`, validate
  that posts/votes parse and persist only the sanitized structural subset.
- Live upvote markup (verified 2026-07-10): `a.post-reputation`, with the
  numeric score in its text and `positive`/`neutral` as presentation classes.
  The thumbs-up/down buttons are actions, not counts. Try `_UPVOTE_SELECTORS`
  first; if real markup differs, record one authenticated fixture and extend
  THAT list only.
- Both the phpBB login-form GET and credential POST go through
  `scrapers/http.py`; the session stays in memory and no `sid`, account label,
  author, location, signature or post body is written to the real fixture.

## Politeness invariants (never relax while debugging)

- All HTTP through `app/scrapers/http.py`: jittered per-domain delays
  (BR 2–4 s, PA 1.5–3 s, default 1–2 s), backoff ×3, hard stop
  (`FetchBlockedError`).
- 24 h cache: never re-fetch a page that succeeded within the window unless
  the user explicitly forces.
- Volumes: full forced refresh = 8 BR pages + 1 archiwum + ≤2 Yahoo tries
  ≈ ≤11 requests over ~30–45 s. Cached refresh ≈ 1–2. Forum sync is
  incremental (~1 page per 50 new posts). The summary's `requests` entry
  shows the count — keep it visible.
- Debugging never means "fetch more": mapping problems are fixed from the DB
  (step 3), markup problems from recorded fixtures (step 4) — one recording,
  many test runs.
