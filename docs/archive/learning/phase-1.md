# Phase 1 — BiznesRadar scraper + prices

## What was built
One polite HTTP path for all scrapers, a single generic parser for every
BiznesRadar `report-table` page, stooq CSV prices, refresh orchestration with
a 24 h cache, and the first real API endpoints (watchlist CRUD + data reads).

## Concepts worth understanding

**Rate limiting + backoff by hand** (`app/scrapers/http.py`) — what Polly
would give you declaratively in .NET, written explicitly (~100 lines) because
the policy is the core requirement: jittered per-domain delays, one retry
ladder, a hard stop (`FetchBlockedError`) that callers must not retry on top
of. Module-level state (`_last_request_at`) is fine in a single process — the
same thing a C# `static Dictionary` would do.

**Parse ≠ interpret** — `scrapers/biznesradar.py` returns labels and numbers
verbatim; `services/fields.py` is the only place that decides "this label
means revenue" (exact normalized match — 'Zysk brutto' and 'Zysk brutto ze
sprzedaży' are different lines). When the site changes wording you extend one
alias tuple; the DB already stores raw labels so nothing needs re-scraping.

**Idempotent upserts** (`services/refresh.py`) — preload existing rows into a
dict keyed by natural key, then update-or-add. Refresh can run any number of
times; the unique constraints are the safety net, not the mechanism.

**Error isolation** — one failed page degrades to a `"balance_q": "error: …"`
entry in the summary instead of failing the whole refresh. The API returns
what happened per page; the UI can show it verbatim.

**Fixture-based tests** — recorded HTML in `tests/fixtures/` makes parser
regressions visible the moment markup changes (like snapshot tests, but
asserting extracted values). End-to-end tests monkeypatch `http.fetch` — the
whole pipeline runs with zero network.

## Where to look
`app/scrapers/http.py` → `app/scrapers/biznesradar.py` →
`app/services/fields.py` → `app/services/refresh.py` → `tests/test_api_phase1.py`.
