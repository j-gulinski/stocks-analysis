# Changelog / decision log

Context ledger for future work: every meaningful change lands here with the
task IDs it implements and any decisions or deviations from PLAN.md.
Format: date · scope · what + why. Newest first.

Enforcement: `.githooks/pre-commit` rejects commits that touch code without
touching this file (`git config core.hooksPath .githooks` after `git init`),
and CLAUDE.md instructs AI sessions to treat a change without an entry as
incomplete.

Older detail: the twelve build-day entries (2026-07-07) are archived verbatim
in `docs/changelog-archive-2026-07-07.md`; their durable technical findings
live in the quirks ledger (`skills/scraper-doctor/SKILL.md`). The digest at
the bottom of this file keeps the decisions scannable.

---

## 2026-07-08 · Data correctness + source rework + dynamic per-company analysis

Big verification round after user testing showed wrong classifications,
missing indicators and dead price sources. Backend + tests; frontend entry
below is part of the same change set.

**Size/mcap correctness (the ">1 mld shown as small" bug):**
- Profile parser now extracts the REPORTED `Kapitalizacja:` and
  `Enterprise Value:` (DOM-first, handles full integers and scaled
  "2,82 mld"; stored via migration 0004 on `companies`). `compute_ttm`
  prefers the reported figure — price×shares stays only a fallback and its
  deviation is exposed (`market_cap_check_pct`), so a stale price or a
  misparsed share count can no longer shrink a company below the small-cap
  threshold. Shares regex requires `:`+digits — the free-float row
  ("Liczba akcji w wolnym obrocie") can't be captured anymore.
- `classify_size` (micro <150 mln / small <1 mld / mid <5 mld / large):
  feeds the prescore evidence ("Kapitalizacja X mln zł (wg BiznesRadar) —
  Średnia spółka; próg 1 mld.") and the insights header chips.
- Self-healing prices: future-dated rows (an old bug wrote them and the
  `last_day >= today` guard then froze the chain on "aktualne" forever) are
  purged on every refresh; future bars are never stored again.

**Missing wskaźniki:**
- `match_indicator` is code-first (`data-field="CZ"`…) with the verified
  exact-label fallback; a guessed code never overrides a live-verified
  label on conflict. New mappings: C/ZO→`czo` (own code — never cz!),
  EV/Przychody→`ev_revenue`, short "Marża netto"/"Marża operacyjna",
  "Marża zysku ze sprzedaży"→`sales_margin`. Deliberately unmapped: Graham
  C/WK and "Marża zysku brutto" (PRETAX margin, not gross-sales).
- Dropped indicator rows are now VISIBLE: refresh summary lists
  "pominięte: …"; mapping-report gained `indicators_never_seen`.

**Comparability between stocks:**
- `load_income_series` is rank-aware: parent-shareholders net profit
  ("akcjonariuszy jednostki dominującej") beats the group row regardless of
  page order → EPS/C/Z now consistent across statement layouts.
- Reverse gross derivation (pos + selling + admin) when a layout reports
  profit-on-sales without a gross row; balance mappings extended with
  section totals (aktywa obrotowe, zobowiązania krótko-/długoterminowe,
  zapasy) for liquidity/gearing ratios.

**Price sources (stooq dead, Yahoo flaky — user-verified):**
- NEW source: BiznesRadar archiwum notowań, PAGE 1 ONLY (~50 sessions) —
  robots.txt allows page 1 and disallows `,N` pagination, so the app never
  paginates. Same politely-fetched domain, `parse_price_history` finds the
  table by header labels.
- Chain rework: incremental = BR archiwum → Yahoo → profile quote (stooq
  SKIPPED daily — it answers "access denied"; knocking daily would be
  impolite); backfill = Yahoo (5y in 1 request) → stooq (one chance) → BR
  archiwum → profile quote. Yahoo hardened: query1+query2 hosts,
  browser-ish headers, no second host after a hard block. Bossa EOD files
  evaluated and rejected (login-gated since 2026). `/health/scrapers` now
  tracks yahoo and both stooq hosts; failures are logged, not just
  successes.

**Dynamic per-company analysis (new `services/insights.py`, pure):**
- Sector groups (finance/biotech_med/tech/energy/realestate/consumer/
  industrial/other from BR "Branża") + size class pick WHICH indicators are
  judged: banks by ROE/C-WK/dividend, biotechs by cash runway, industrials
  by gross-margin trend/operating leverage, energy by EV/EBITDA/debt…
  Each indicator gets a verdict (plus/neutralnie/minus) with a Polish
  one-liner tied to this company's numbers.
- Honesty rules: missing data lands in `missing[]` with WHY it matters —
  never fabricated; `data_notes` flag stale price, derived mcap,
  reported/derived divergence >20%, financial-statement layout; `coverage`
  says how many of the selected indicators were computable.
- **Summary is COMPOSED from computed values** (user feedback on the first
  iteration: template counts like "3 na plus" are useless) — e.g. "Duża
  spółka, energetyka / surowce (156,98 mld zł). Na plus: EV/EBITDA 5,8;
  one-offy 8,3% zysku oper.; dywidenda 27 lat z rzędu. Na minus: C/Z 24,5
  vs własna mediana 7,8; ROE 4,3%." Only metrics that exist appear.
- Dossier gained `insights`; schemas + TS types extended accordingly.

**Tests:** suite updated for all of the above; new `test_insights.py`,
`test_refresh_prices.py` (chain order, stooq-skip, future-purge),
parser tests for mcap/EV/free-float/scaled forms + price history; fixtures
extended with trap rows (free float, Graham, pretax margin). Pure layers
(fields/metrics/insights/parsers) executed green in-session against fixture
+ live-shape data; DB/API layers compile-checked — run `cd backend &&
pytest` locally (sandbox has no PyPI). Real-page recording:
`python scripts/record_fixtures.py SNT` now also records the archiwum page.

**Memory consolidation (user request):** CLAUDE.md trimmed to a short
always-loaded core with an on-demand doc index; build-day changelog entries
archived to `docs/changelog-archive-2026-07-07.md` with a digest below;
quirks ledger restructured (BR items unmisfiled from the Prices section,
chain-order contradiction resolved, 2026-07-08 findings added).

## 2026-07-08 · Frontend: dynamic insights panel + mcap provenance notes

Frontend side of the sector/size-aware analysis (`insights` block in the
dossier API):

- **types.ts** mirrors the new backend shapes: `Company.market_cap` /
  `enterprise_value`, `Ttm.market_cap_source` ("reported" | "derived") +
  `market_cap_check_pct`, and `Dossier.insights` (`Insights`, `KeyIndicator`,
  `MissingIndicator`). Indicator values arrive preformatted as strings —
  rendered as-is, no client-side number formatting.
- **New `InsightsPanel`** on the Przegląd tab, ABOVE the prescore (dynamic
  analysis is the entry point, the static checklist follows): size/sector
  chips + summary, key indicators sorted by importance (imp. 3 tagged
  "kluczowy", verdict badges plus/neutralnie/minus/b-d), Mocne strony /
  Ryzyka in a `grid-2`, "Czego brakuje w danych" prefixed with the coverage
  note, and warning-toned `data_notes` at the bottom. Empty sections are
  skipped.
- **globals.scss:** added `.badge.neutral` / `.badge.muted` variants (the
  verdict palette needed non-signal tones) and a scoped `.insights` block —
  hairline dividers between sections inside one card, list markers colored
  by verdict instead of the text.
- **MetricCards:** the Kapitalizacja card now footnotes provenance —
  "szacunkowa (kurs × liczba akcji)" when the value is derived, and a warn
  note "rozbieżność źródeł X%" when the reported/derived gap exceeds 20%.

Verified with `tsc --noEmit` and a standalone `sass` compile (no dev server
in this environment).

---

## 2026-07-07 · Consolidated digest — build day (full text in `docs/changelog-archive-2026-07-07.md`)

One day, twelve entries: planning → scaffold → scrapers → analytics →
frontend → five production-debugging rounds on real tickers (SNT, CBF, DEC).
Decisions that still govern the code:

- **Architecture:** monorepo FastAPI + Next.js; PostgreSQL (SQLite in
  tests); scrapers fetch+parse+upsert only; metrics/forecast pure functions;
  one polite fetch path (`scrapers/http.py`, jittered per-domain delays,
  backoff, hard stop); 24 h page cache; changelog discipline + pre-commit
  hook; learning notes per phase (C# analogies).
- **Production topology:** Vercel + Railway, Auth.js Google allowlist,
  browser→backend only via the Next proxy with a static bearer (Phase 6).
- **Units:** statements tys. PLN; price PLN; mcap PLN;
  `eps = ttm × 1000 / shares` in exactly one place.
- **The big scraping discoveries** (all in the quirks ledger): BR slug
  redirect drops `,Q` (→ `companies.br_slug`, migration 0003); explicit
  `,Q`/`,Y` always; header-row scan + "Data publikacji" exclusion;
  `IncomeGrossProfit` actually = profit-on-sales; data-field codes are row
  identity; replace-semantics on forced refresh + ON CONFLICT upserts after
  two UniqueViolation crashes; stooq denies non-browser clients (HTTP 200
  body!); Yahoo added as price source; profile quote as last resort;
  long-form indicator labels ("Cena / Zysk") with tightened slashes.
- **Product decisions:** English nav labels, Polish domain data; refresh
  summaries with shape+range detail; `requests: ok (n HTTP)` transparency;
  diagnostics endpoints (`/health/scrapers`, mapping-report); forum upvotes
  groundwork (migration 0002); P1.9 BR premium login and P5.9 forum
  distiller planned; ESPI/EBI poller + hotness backtests parked as
  extensions.
