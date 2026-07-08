# Changelog / decision log

Context ledger for future work: every meaningful change lands here with the
task IDs it implements and any decisions or deviations from PLAN.md.
Format: date · scope · what + why. Newest first.

Enforcement: `.githooks/pre-commit` rejects commits that touch code without
touching this file (`git config core.hooksPath .githooks` after `git init`),
and CLAUDE.md instructs AI sessions to treat a change without an entry as
incomplete.

Older detail is archived verbatim, newest stage first: the closed Stage-TH
entries (2026-07-08) in `docs/changelog-archive-thesis-2026-07-08.md` and the
twelve build-day entries (2026-07-07) in `docs/changelog-archive-2026-07-07.md`;
their durable technical findings live in the quirks ledger
(`skills/scraper-doctor/SKILL.md`). The two digests at the bottom of this file
keep the decisions scannable.

---

## 2026-07-08 · Frontend UX merge — decision workspace direction

Merged the Codex frontend refresh into the project repo and set the next product
direction: the stock page should read as an analyst workspace, not a dump of
every scraped field. The UI now prioritizes thesis, valuation/scenarios,
evidence, and drill-down tabs; wide financial tables scroll inside their own
container instead of stretching the whole page; stock pages keep Watchlist nav
context; and the AI-analysis action opens the dedicated tab instead of making a
daily-capped call from the header.

Follow-up focus from user feedback: make deletion hard/truthful because stale
company data survives watchlist removal; make newly-added tickers show an honest
"needs refresh/no dossier yet" state instead of misleading blanks; expose API-key
diagnostics for AI analysis; and continue reorganizing collected data into
decision-oriented groups.

## 2026-07-08 · Skill broadened — combined multi-practitioner factor lens (Areczeks + Elendix)

`skill/SKILL.md` gains a **"Broader factor lens — complementary GPW
practitioners"** section, distilled from two PortalAnaliz portfolio threads
(Areczeks t=575; Elendix "Inwestowanie w szanse" t=356), read via the logged-in
browser (sandbox egress to portalanaliz.pl is proxy-blocked, so web_fetch/the
scrapers couldn't reach them; the Chrome extension could). Goal per user: make
the analysis weigh *many* factors, not Malik's alone.

- **Design decision — Malik stays the scoring spine.** The new factors enrich
  `checklist` / `catalysts` / `red_flags` / `verify_next`; `alignment_score`
  stays anchored to the computable Malik factors + `rubric.md`. Any added factor
  the dossier can't compute is `nieznane` (drops out of the denominator per the
  unknown≠fail rule), never a failure — so the lens widens the narrative and
  makes gaps explicit without loosening the number. Frontmatter + intro updated
  to say so.
- **Factors added:** a multiple set beyond C/Z (EV/EBITDA, ROE, C/WK, płynność,
  zadłużenie, 5-yr CAPE, PEG<1, C/P & "cena za aktywnego klienta", EV adjusted
  for held stakes/cash); net-cash-vs-cap deep value + Lynch no-debt guard;
  one-off normalization; capital-return policy (buyback+dividend) as a quality
  signal; insider / major-shareholder cost-basis anchoring. New catalyst types
  (policy/macro programmes, regulatory/trade events, launch event-modelling that
  maps onto the `scenarios` block, contrarian "o spółce jest cicho" low-attention
  signal). Sharper red flags (insider selling while claiming long-term; negative-
  surprise management kept small even when cheap; political/regulatory overhang;
  paying up for growth vs a cheaper peer; retail hype/extrapolated targets;
  behavioural bias / "miłość do spółki"). Portfolio/behavioural discipline (ride-
  winners vs sell-half-at-+100%; ≤20–25% position caps; 10–15% cash reserve;
  benchmark-vs-sWIG80TR honesty) — flagged portfolio-level → `verify_next`, never
  the per-stock score. Faithful short Polish quotes retained for citation.
- **Caveat / follow-up:** the Elendix thread capture covered only its most recent
  page (~6 weeks of a 374-post thread); Areczeks ~84%. The factor set is
  representative but Elendix's full history (position-sizing evolution etc.) is
  not yet mined — offer to fetch earlier pages if deeper coverage is wanted.
  Sources are opinion threads, cited as such; `docs/strategy-malik.md` remains
  the primary source-cited spec and wins on any conflict.

## 2026-07-08 · P5.7 Analiza AI tab + P5.9 forum distiller (Phase 5 nears complete)

**P5.7 — Analiza AI tab (frontend).** Wired the AI-analysis tab into the stock
page: new `AnalysisPanel` (run button → `runAnalysis`; loads history on mount;
verdict card with tone-coloured alignment_score headline, thesis, catalizatory,
checklist with spełnia/nie spełnia/nieznane icons, red flags, one-off risk,
potencjał, forum insights labelled "opinie nie fakty", verify_next, summary_pl,
disclaimer; history table with **score-delta + per-item checklist-change diff**
vs the previous run). `Analysis`/`AnalysisVerdict` types mirror backend
`AnalysisOut` + the `zapisz_analize` tool schema; `api.ts` gains `runAnalysis`/
`listAnalyses` through the same `/api/...` proxy; 429/503 render the backend's
Polish `detail` in `.error-box` (503 reads as intentional config state). New
`.analysis` SCSS scope follows the self-contained `.thesis`/`.scenarios` card
convention (colours all `--text-*`). Header Sparkles button now **switches to
the tab** rather than auto-running, so the daily-capped AI call stays an
explicit action. Added `"AI analysis"` to `TABS`, removed the disabled
placeholder. `tsc --noEmit` exit 0.

**P5.9 — Forum distiller (backend).** `services/forum_distiller.py`: a
cheap-model classification/claim-extraction pass over posts **already synced in
the DB** (zero new forum HTTP). Each post → {fact-claim|opinion|question|noise}
+ extracted claims with confidence, **cached per post** (file cache
`backend/.cache/forum_claims/`, keyed post-id+content-hash+model — no
migration). `distill_company_posts` merges into a deduplicated (union of
source_post_ids), upvote-weighted (reuses `forum.py sort=top` ordering),
budget-truncated `DistilledClaim` list. No key / any failure degrades a post to
an empty distillation — never raises, so the verdict run always completes.
`config.py` gains `ai_distill_model` (default `claude-haiku-4-5`, cheaper than
the verdict model). `prompts.build_analysis_prompt` gains an optional keyword
`forum_claims` (preferred path — claims labelled confidence + source post ids,
marked "opinie nie fakty"); `forum_posts` stays as a backward-compatible legacy
fallback, so `test_analysis_ai.py` is unchanged and green. `api/analyses.py`
distils fetched posts before building the prompt — the verdict never sees raw
post text as fact. `tests/test_forum_distiller.py` 15 pure tests green;
`test_analysis_ai.py` 17/17 still green (no regression).

## 2026-07-08 · Phase 5 wired — Claude client, prompt assembly, analysis endpoints (P5.4–P5.6)

Module D goes from reviewable skill docs (P5.1–P5.3) to an actually-callable
analysis pipeline: dossier + forum → prompt → forced-tool-use Claude verdict →
persisted `Analysis` row, behind a global daily cap.

- **`services/claude_client.py` (P5.4).** `run_analysis()` — its own transport
  (SDK-or-urllib, same dual-path shape as `thesis_ai.default_transport`) but
  forcing structured output via `tool_choice` on a `zapisz_analize` tool whose
  `input_schema` mirrors the PLAN §8 verdict shape exactly. Bounded retry (3
  attempts); best-effort response cache under `backend/.cache/analysis/` keyed
  by ticker+prompt-hash+model. Unlike `thesis_ai`/`scenarios_ai`/
  `valuation_ai`, there is no deterministic verdict to fall back to — no key,
  exhausted retries, or an unparsable response all raise `AnalysisUnavailable`
  rather than fabricate output; `anthropic`/`pydantic_settings` stay
  import-lazy (verified in a fresh subprocess).
- **`services/prompts.py` (P5.5).** `build_analysis_prompt()` assembles
  `system` = `skill/SKILL.md` + `skill/rubric.md`; `user` = a deterministic
  (sorted-key) pretty-JSON slice of the dossier's decision-relevant fields
  (prescore/ttm/pe_history/net_cash/insights/thesis/scenarios/valuation/
  latest_forecast) + recent forum posts newest-first, explicitly labelled as
  unverified opinions, capped at ~30k chars with a truncation marker. Returns a
  `snapshot` of exactly what was sent.
- **`api/analyses.py` (P5.6).** `POST /api/companies/{ticker}/analyses`:
  404 unknown ticker → global daily cap (`settings.ai_daily_limit`, 429 Polish
  message) → dossier + up to 40 recent forum posts → prompt →
  `claude_client.run_analysis` → 503 ("Analiza AI wymaga skonfigurowania
  ANTHROPIC_API_KEY.") on `AnalysisUnavailable` → persists an `Analysis` row
  (model, prescore, output=verdict, alignment_score, tokens, created_by).
  `GET .../analyses` returns history newest-first. Registered in `app/main.py`;
  `AnalysisOut` DTO added to `api/schemas.py` (permissive `output: dict`).
- **Decision: no new migration.** `alembic/versions/0001_initial.py` already
  creates the `analyses` table matching the `Analysis` model column-for-column
  (added ahead of schedule with the model) — confirmed by hand diff;
  `alembic upgrade head` stays at `0004`, `test_migrations.py` needs no change.
- **Tests: `tests/test_analysis_ai.py`** — 17 pure tests pass under bare
  `PYTHONPATH=. python3 tests/test_analysis_ai.py` (import hygiene via
  subprocess isolation, deterministic prompt assembly incl. dossier-key
  filtering / forum ordering / truncation, forced tool-use parsing + token
  extraction, no-key & malformed-response `AnalysisUnavailable`, retry-then-
  succeed & retry-exhausted, cache hit/skip); 4 client-gated tests (happy
  path / 503 / 429 / 404) deferred to `pytest` on the user's machine.
- **Known gap:** the `Analysis` table has no column for the prompt `snapshot`
  (only prescore/output/token counts per the existing model) — reproducibility
  data is available at call time but not persisted; a future migration could
  add it if cross-run diffing becomes a real workflow.

## 2026-07-08 · P1.9 BiznesRadar premium session — scaffolded (real login deferred)

Plumbing for an optional logged-in BiznesRadar session (premium = longer report
/ price history), built without hard-depending on it — anonymous refresh is
byte-for-byte unchanged when no credentials are set.

- **`scrapers/biznesradar.py`** — added `BrLoginError`, `extract_login_fields()`,
  `_looks_logged_in()`, and `class BrClient` (a `requests.Session` wrapper
  mirroring `portalanaliz.ForumClient`), all HTTP via
  `http.fetch(..., session=self.session)`.
- **`config.py`** — added `br_username` / `br_password`.
- **`services/refresh.py`** — `_build_br_session(summary)` logs in only when
  creds are configured and **never aborts** on failure (sets
  `summary["br_login"]` = ok/error/"pominięto (brak danych logowania)" and
  continues anonymously); an optional `session` param is threaded through
  `_get_page` / `_refresh_profile|_reports|_indicators|_dividends` /
  `_fetch_br_history` / `_refresh_prices`. `check_br_login()` diagnostics mirror
  the forum login-status.
- **`api/diagnostics.py`** — `GET /api/diagnostics/br-login-status` (deliberately
  under diagnostics, not `/companies/...`, to avoid being swallowed by
  `GET /companies/{ticker}`). `.env.example` activates `BR_USERNAME/BR_PASSWORD`;
  `conftest.py` neutralises them so a real local `.env` can't trigger a live
  login in tests.
- **Test:** `tests/test_br_login.py` + synthetic `tests/fixtures/br_login.html`
  (clearly marked synthetic). `extract_login_fields`, login success (exact
  payload/URL), and failure paths verified by replaying the assertions directly
  (needs-only requests+bs4); endpoint test + full suite need the user's venv.
- **UNVERIFIED — deferred to the user's machine.** BiznesRadar's real login-page
  markup was unreachable in the sandbox (egress blocked), so
  `extract_login_fields` / `BrClient.LOGIN_PATH` (`/logowanie`) / field names /
  success-check are best-effort guesses tested only against the synthetic
  fixture. On login failure `BrClient` raises (safe: refresh degrades to
  anonymous) rather than silently mis-scraping. Next: record a real BR login
  page, correct the parser, and confirm one real login. P1.9 stays **scaffolded,
  not done**.

## 2026-07-08 · Phase 5 started — strategy skill authored (P5.1–P5.3), pre-wiring review gate

The reviewable half of Module D: the plain-markdown strategy skill that becomes
the Module D analysis system prompt. Authored from the source-cited spec
(`docs/strategy-malik.md`) + a fresh mining pass over `obs.txt` /
`Filozofia_…OBS_Portfel_IKE.md` for real worked cases. **Not wired into any
code path yet** — P5.1 mandates "review together before wiring", so
`claude_client.py`/`prompts.py`/endpoints/tab (P5.4–P5.7) are deliberately not
started.

- **`skill/SKILL.md` (P5.1).** Analyst instructions: three load-bearing ideas
  (stock-picking not timing; sprawozdania/P&L-first with marża brutto + dźwignia
  operacyjna as the motors; teza-first + catalyst + quarterly re-verify); the
  small-cap edge; a compiled "7 golden rules"; the 16-principle checklist mapped
  to concrete dossier fields **or** labelled gaps; a catalyst taxonomy
  (operational / order-book / cyclical / capital-structure / corporate-event +
  a priced-in test); one-off-vs-sustainable guidance; red flags; the valuation
  doctrine (forward C/Z < 0.85× own median, margin-of-safety trio); the
  entry-quality reference mirroring the deterministic engine; the six
  never-fabricate gaps → `verify_next`; forum-claims-are-opinions rule; and the
  PLAN §8 output contract. Domain terms Polish, `summary_pl` Polish.
- **`skill/rubric.md` (P5.2).** Weighted 0–100 score with the load-bearing
  **"unknown ≠ fail"** rule: items are spełnia/nie spełnia/**nieznane**, and
  `nieznane` items are dropped from the denominator (never scored 0) so our data
  gaps don't sink every company. Weights follow Malik's priorities (margin trend
  15, valuation-vs-own-history 15, revenue 12, op-leverage 12, profit-quality
  12, catalyst 10, …). Vetoes/caps: one-off-profit veto (cap 50), net-loss+net-
  debt veto (cap 40), no-catalyst cap (75, encoding "cheap ≠ sufficient");
  < 3 computable indicators ⇒ `insufficient_data`, no number. Bands + an
  explicit "stay consistent with the engine's `entry_quality`" clause.
- **`skill/examples/` (P5.3).** Three real cases as few-shot verdict shapes,
  incl. **one documented miss** so the model learns the failure mode:
  `optex.md` (cheap forward C/Z + quantified backlog catalyst + sell-when-
  catalyst-stops → +100%/6mo), `toya.md` (durable discount + buyback as active
  catalyst; forward C/Z 10 ⇒ ~950 mln vs ~733 mln cap), `suntech.md` (narrative
  "new contracts" catalyst that kept failing, held via rationalisation — Malik's
  own confessed *"samousprawiedliwienie błędnych decyzji"*), + a README.
- Scope: docs/skill only, no code, no schema, no HTTP. Next (after review):
  P5.4 `claude_client.py` reuses the TH.2b `thesis_ai` transport/cache; P5.5
  `prompts.py`; P5.6 endpoints + `analyses` table + `AI_DAILY_LIMIT`; P5.7
  Analiza AI tab.

## 2026-07-08 · Fix 4 pre-existing DB/API test failures surfaced by first full `pytest` run

The Stage-UX/SC work was verified in-sandbox with a pytest *shim* (no PyPI/DB);
the first real `cd backend && pytest` on the user's machine (204 passed / 6
skipped) surfaced 4 failures — none a product regression, both classes
pre-existing and only reachable with the real DB/TestClient the sandbox lacks.

- **`test_api_phase1.py::test_force_refresh_replaces_stale_periods` — stale
  assertion, not a regression.** It asserted the refresh summary
  `.startswith("ok (99 values)")` with a closing paren, but `refresh.py:372/344`
  intentionally enriches the summary with table detail — `ok (99 values; 11
  rows × 9 periods; 2023Q1–2025Q1)` — so the `)` stopped matching. The
  enrichment is the current, intended behaviour (`_table_detail`); the test
  predates it. Fixed by matching the stable prefix `"ok (99 values"` (still
  catches a DB error or wrong count).
- **`test_module_imports_without_pypi` in test_thesis_ai / test_scenarios_ai /
  test_valuation_ai — test-isolation bug, not a broken lazy-import.** Each
  asserted `"pydantic_settings" not in sys.modules`. The lazy-import property
  is real (the modules don't import it at top level; the tests pass in
  isolation), but under the *full* suite an earlier test imports `app.config`
  (which does `from pydantic_settings import BaseSettings`), leaving it in the
  shared `sys.modules` — so the in-process assertion was order-dependent.
  Fixed by probing in a **fresh subprocess** (`python -c "import
  app.services.<mod>; assert 'pydantic_settings' not in sys.modules"`,
  cwd=backend), which actually enforces "importing *us* pulls neither dep"
  regardless of suite order — and still fails loudly if someone adds an eager
  `import pydantic_settings`/`anthropic` to the module. `anthropic` assertion
  unchanged (it was never installed, so never polluted).
- Scope: 4 test files only, no product code touched; `py_compile` green on all
  four. Re-run `cd backend && pytest` to confirm 208 passed / 6 skipped.

## 2026-07-08 · UX/UI pass over the whole flow + two pl-PL cosmetics fixed at root (Stage UX, Part A)

Frontend readability/hierarchy pass with the new thesis + scenario features,
plus the two long-flagged cosmetic bugs fixed **at their backend source** (not
patched in the UI). No architecture change; the plan-fixed Overview order
(MetricCards → Teza → Scenariusze → Analiza → Prescore → Kurs) is kept.

**Backend root-cause fixes (services layer, pure fns — tests stay green):**
- **`strategies/malik.py` — "Mała spółka (Mała spółka)" duplication.**
  `size_pro_text`/`size_con_text` hardcoded the size-class word *and* injected
  `{size}` (the company's size label), so a small cap rendered "Mała spółka
  (Mała spółka) — sweet spot…" and a moloch "Duża spółka (Duża spółka) — …";
  micro/mid were even wronger ("Mała spółka (Mikro spółka)", "Duża spółka
  (Średnia spółka)"). Fix: drop the hardcoded word, let `{size}` carry the real
  label once, and reword the con size-agnostically ("większe spółki są lepiej
  pokryte…") so **all four** sweet-spot/penalised sizes read correctly.
  `base.py` docstring gained a one-line "don't repeat the class word" guard.
- **pl-PL decimal comma unified everywhere numbers are displayed** (the "+1.8"
  vs "+1,8 p.p." bug). Root cause: `insights.py` printed the margin-trend p.p.
  in the *comment* with `:+.1f` (dot) while the *summary brief* used
  `.replace(".", ",")` (comma) — the two disagreed on the same card; runway
  years and the liquidity ratio had the same dot/comma split; and **all**
  `metrics.py` prescore evidence used dots (`_fmt` was `:g`, others raw `:.1f`).
  Fix: one comma convention through small shared helpers — `insights._signed`
  (+ reuse of `_fmt_x`), and `metrics._num`/`_signed_pct` (+ `_fmt` now commas);
  every displayed decimal now matches `pl-PL` like the rest of the app. Integer
  percentages (`:+.0f%`) were already correct and left as-is.
- **Tests (+3, pl-PL + no-dup regression locks):** `test_thesis.py`
  `test_size_factor_label_not_duplicated` (pro/con carry the label once);
  `test_metrics.py` `test_prescore_evidence_uses_pl_decimal_comma`
  (`"Ostatnie 2 kw.: +10,0% i +14,0%."`, one-off "1,1%");
  `test_insights.py` `test_gross_margin_trend_uses_pl_decimal_comma` (comment
  "+1,5 p.p." == summary brief, no "+1.5").

**Frontend (visual hierarchy · colour semantics · degraded states · mobile):**
- **`ThesisPanel` — verdict as a hero.** The entry-quality verdict was a small
  pill equal in weight to the meta chips; now it leads the card as an icon +
  large label (`.thesis .verdict`, tone-coloured). The **icon is a non-colour
  cue** (`IconCircleCheck`/`IconCircleDot`/`IconAlertTriangle`/`IconHelpCircle`)
  so the verdict never relies on colour alone; strategy/engine demoted to muted
  chips.
- **`ScenariosPanel` — valuation made primary.** Added a `.scenarios .headline`
  at the top of the card: the probability-weighted **Oczekiwany potencjał** as a
  26 px signed number (colour + sign) with the `bieżący → oczekiwany` price
  reconciliation; a `.headline-gap` amber note ("wycena niedostępna — brak ceny
  docelowej…") for the no-priced-scenario case. Removed the now-redundant bottom
  "Wartość oczekiwana" strip (folded into the headline) — the per-scenario rows
  read as the supporting detail. All numbers still via `lib/format.ts`
  (`fmtPct`/`fmtPln`/`signClass`) — no raw `toFixed`/`Intl` in components.
- **Degraded state — stale price.** Stock header shows a `kurs sprzed N dni`
  warning badge when the quote is >5 days old, so the scenario valuation
  (computed off that price) is read with the caveat rather than trusting it
  silently. (No-key state needs nothing new: thesis/scenarios/valuation always
  render deterministically; the `silnik: deterministyczny` chip + the disabled
  "Analizuj — Faza 5" button already read as intentional.)
- **Responsive (phone).** Stock header `.spread` now wraps (`flexWrap`); the
  ~10-column watchlist table is wrapped in a new `.table-wrap` (horizontal
  scroll) instead of overflowing the viewport; the forecast form/result grid
  used an inline `gridTemplateColumns` that defeated the mobile 1-col collapse —
  moved to a `.grid-2.wide-left` class with a real `@media(max-width:760px)`
  override.
- **`globals.scss`** carries all new tokens/classes (`.thesis .verdict`,
  `.scenarios .headline`, `.grid-2.wide-left`, `.table-wrap`) — every colour a
  `--text-*` variable; nav labels stay English per the standing user decision,
  domain copy Polish.

Verification (in-session): backend pure suite **126 passed / 0 failed** via the
`/tmp` pytest shim (test_thesis 14, test_thesis_ai 17, test_metrics 21,
test_insights 16, test_forecast 5, test_scenarios 14, test_scenarios_ai 14,
test_valuation_ai 25 — +3 vs the 123 baseline, no regression); `py_compile`
green on the four touched backend files; `tsc --noEmit` exit 0; `sass` compile
of `globals.scss` exit 0. Deferred to the user's machine (no PyPI/DB/egress in
sandbox): `cd backend && pytest` full DB/API suite; `cd frontend && npm run
build`; and real-browser rendering of the hero/headline/stale-badge + the
mobile watchlist scroll.

### Part B — static previews of the post-Part-A panels (real engine output)

Visual previews of the redesigned **Teza inwestycyjna** + **Scenariusze** cards
for the user, filled with REAL deterministic engine output (no hand-typed
numbers), under `docs/previews/`. Rationale: let the user see the Part A
hierarchy/colour changes on a concrete company before the DB/API path is run on
their machine.

- **Data path (no invented numbers).** `docs/previews/_render_engine_output.py`
  rebuilds the *pure* half of `dossier.build_dossier` (parsers → `fields` →
  `metrics` → `insights` → `thesis` → `scenarios` → `valuation_ai`, exactly like
  `scripts/validate_thesis.py`) on the committed **DECORA (DEC)** fixtures
  (`backend/tests/fixtures/br_*.html`; identical to
  `backend/.cache/validation/DEC_*.html`). The one deliberate divergence from
  `validate_thesis.py`: the current price is sourced the way `dossier.py` sources
  it (stored Price rows) — here the committed `stooq_daily.csv` latest close
  **24,50 zł**, which equals DECORA's reported market cap ÷ shares — so the panel
  renders with a live weighted potential instead of a `None` price. Every AI
  refiner runs on its **no-key deterministic** path. Output →
  `docs/previews/dossier-DEC.json` (thesis + scenarios + valuation + insights).
- **Real engine numbers (DEC, Malik/OBS).** verdict `attractive` ("Ciekawy punkt
  wejścia w analizę"); C/Z reversion (own history median 11,35 / q1 10,78 / q3
  11,85, n=8; eps 2,545; price 24,50); scenarios −/base/+ = 27,44 zł (**+12,0%**)
  / 28,89 zł (**+17,92%**) / 30,16 zł (**+23,1%**), p 0,25/0,50/0,25; weighted EV
  **28,84 zł (+17,71%)**; valuation potential **+17,71%** (pasmo +12,0…+23,1%),
  confidence **high** (7 key indicators ≥5, n=8 ≥4).
- **Render vehicles.** `scenarios-DEC-after.html` — self-contained (CSS compiled
  by hand from `globals.scss`, DOM mirrors `ThesisPanel.tsx`/`ScenariosPanel.tsx`
  1:1, numbers via the `lib/format.ts` pl-PL rules, zero external requests,
  viewport set → opens on a phone). `scenarios-DEC-after.png` (+ `.svg` source) —
  a native-SVG render rasterised with ImageMagick, because the sandbox has **no
  headless browser** (no chromium/playwright; `pip` egress 403) and ImageMagick's
  MSVG ignores `<foreignObject>`, so HTML can't be screenshotted; the PNG is a
  faithful *static* preview, the HTML is the pixel-faithful one. Generators
  `_render_html.py` / `_render_svg.py` kept next to the previews for
  reproducibility.
- **Deliberately skipped.** A pre-Part-A "before" variant: `ThesisPanel.tsx` /
  `ScenariosPanel.tsx` are **untracked** (created in Stage TH/SC), so `HEAD` has
  no earlier version to diff against — not recoverable from git. **SNT** preview:
  only a markdown web-extraction exists (`fixtures/live-20260708/SNT_*.md`), which
  the BeautifulSoup parsers can't read (per `docs/validation-thesis.md`) and which
  carries no C/Z history — so no real scenario set is computable; DEC is the one
  committed fixture-backed ticker that runs the full pipeline. (`docs/previews/`
  also holds four zero-byte `_inspect_*.png` stubs — leftover crop scratch the
  sandbox FUSE mount refused to `unlink`; safe to delete.)

## 2026-07-08 · Stage SC complete — scenario simulation engine + AI valuation agent (WP5 closeout, SC.1–SC.5)

Final in-session conformance pass for stage SC (`docs/plan-stage-scenarios.md`).
Per-WP entries already exist below (WP1 memory compaction, WP2 cleanup, WP3
scenario engine, WP4 valuation agent + corpus); this entry is the stage-level
digest + honest final numbers per plan §WP5.

**Exact test counts (this session, shim rebuilt from scratch in `/tmp`; repo
untouched):** 176 passed / 0 failed / 0 error / 29 skipped across 15
importable files, + 2 genuine collection errors. Per file: `test_thesis` 13,
`test_thesis_ai` 17, `test_metrics` 20, `test_insights` 15, `test_forecast` 5,
`test_biznesradar_parser` 33 (+6 skip — `real_br_*.html` never recorded),
`test_http` 6, `test_stooq` 8, `test_forum` 3 (+3 skip — needs FastAPI
`TestClient`), `test_yahoo` 3 (+2 skip — needs `TestClient`/SQLAlchemy `db`),
**`test_scenarios` 14** (13 from WP3 + 1 new WP5 regression test, ≥9
required), **`test_scenarios_ai` 14** (≥10 required), **`test_valuation_ai`
25** (≥8 required, incl. corpus-integrity tests); `test_api_phase1` 0+12 skip,
`test_api_phase3` 0+6 skip (both need `TestClient` per-test, not collection
errors this run — see methodology note in `docs/validation-scenarios.md`);
`test_migrations`/`test_refresh_prices` genuine collection errors (`import
sqlalchemy`/`alembic` at module top). **Stage-TH baseline unchanged**
(thesis/thesis_ai/metrics/insights identical counts) — no regression.
`py_compile` 65/65 (whole backend) / 41/41 (`app`+`scripts`, same baseline
subset as after WP4). `tsc --noEmit` exit 0.

**Defect found and fixed this session (not just documented).** Cross-checking
a scenario built from DEC's real fixture numbers (own C/Z history + EPS from
`docs/validation-thesis.md`, but — as that doc already notes — no price in the
fixture) crashed `services/scenarios.py` with a `TypeError`: `_build_scenario`
only routed to its "labelled gap" branch when `target_price`/`mult_value` were
missing, never when `current_price` alone was missing while a target price
was still computable. The narrative formatter then tried `_fmt_signed(None)`.
In production this is reachable whenever a company has computable
EPS/book-value/EBITDA but no price at all (every price source failed one
refresh, or a fresh listing) — `dossier.py` calls `build_scenario_set`
unconditionally, so this would 500 the whole `/api/companies/{ticker}`
endpoint, not just degrade the scenarios section. Fixed with a minimal added
branch (labels the missing-price gap instead of formatting `None`; the
current-price-present branch is byte-for-byte unchanged) plus a new regression
test, `test_missing_current_price_labels_gap_no_crash`
(`tests/test_scenarios.py`, now 14/14). Full suite re-confirmed green after the
fix (176 passed, up from 175 before this test existed). Full write-up incl.
root cause: `docs/validation-scenarios.md` §"Defekt znaleziony i naprawiony".

**Fixture-first policy confirmed.** `test_scenarios.py`/`test_scenarios_ai.py`/
`test_valuation_ai.py` use exclusively hand-built `ScenarioInputs`/
`StubTransport` — zero live HTTP in the test suite itself.

**Live BR validation: attempted, deferred (precise reason, not silently
skipped).** One polite request this session through `app.scrapers.http.fetch`
(the same path production uses, no bypass) to
`https://www.biznesradar.pl/notowania/DEC` → `FetchBlockedError` (proxy 403 on
CONNECT), matching stage TH's finding exactly; not retried, archiwum untouched,
0 pagination. Scenarios/valuation add no new scraping surface (plan
§Non-goals) — they consume already-computed dossier fields — so a live probe
here would only re-exercise the already-documented parser limitation from
`docs/validation-thesis.md` (`web_fetch` reaches BR but returns markdown, not
HTML); not repeated, reasoned out explicitly in the validation doc instead of
silently reusing the old finding.

**Docs written.** `docs/validation-scenarios.md` (hand-checked cz/cwk/ev_ebitda
target/upside/weighted-EV numbers reproduced by a live run this session, not
copied from test comments; probability-coherence + multiple-selection checks;
confidence-heuristic worked examples at all 3 levels; corpus enrichment
summary incl. the SUNTECH miss; the defect write-up; exact test counts;
explicit gaps/deferred section). `docs/learning/phase-scenarios.md` (≤1 page,
5 concepts incl. the strategy-pattern projector, the `compute_pe_history` →
`compute_multiple_history` alias, the widened AI fabrication guard, probability
renormalisation, the confidence rules-table, and the WP5 debugging lesson;
C#/.NET analogies throughout per CLAUDE.md's learning-layer rule).
`TASKS.md` Stage SC boxes SC.1–SC.5 ticked (all WPs verifier-passed). CLAUDE.md
"Read on demand" index already listed `docs/plan-stage-scenarios.md` +
`docs/validation-scenarios.md` + `docs/learning/phase-scenarios.md` since WP1
(SC.1) — re-checked, still accurate, still 69/70 lines; no further edit needed.

**User-machine runbook (deferred, documented not skipped):** `cd backend &&
pytest` (full DB/API suite, 24 tests); `cd frontend && npm run build`;
`ANTHROPIC_API_KEY=… python scripts/scenarios_smoke.py <TICKER>` (real Claude
refinement for both scenarios and valuation); live BR cross-check for
DGN/OPTEX/SUNTECH entry-era fundamentals via `scripts/validate_thesis.py`.

Why / decisions:
- **Debugging counts as testing (plan's own model split).** The plan assigns
  "testing/debugging/verification" to this WP5 pass; the current-price crash
  was found and fixed here rather than left as a passive note, because it is a
  small, well-contained, test-covered fix squarely inside that remit — not a
  redesign of WP3's already-verifier-approved engine.
- **Honesty over convenience in test-count methodology.** This session's shim
  reports client/db-gated tests as individual skips (with a precise per-test
  reason) rather than blanket per-file collection errors; the *outcome*
  (deferred to the user machine) is identical to earlier sessions, only the
  reporting granularity differs — called out explicitly so the numbers are
  never mistaken for a silent change in what's covered.
- **No new live BR probe beyond one reconfirmation.** Stage SC adds no new
  scraping surface; repeating the already-documented `web_fetch`
  markdown-vs-HTML finding would burn a live request for zero new information,
  so this session did the cheaper, still-honest thing: one polite
  `scrapers/http.py` attempt to reconfirm no egress, and an explicit
  explanation of why a second `web_fetch` probe was skipped rather than just
  silently omitted.

Refs SC.1–SC.5 (stage SC complete, all 5 WPs verifier-passed across the
session history; this entry closes the stage per plan §WP5 acceptance).

## 2026-07-08 · AI valuation agent + WorkedCase enrichment (WP4 / SC.4)

An API-agent step that reads **all gathered data + the WP3 scenario set** and
produces a **stock-potential valuation** (how much potential, at what confidence,
what would change it), plus a real-multiples/repricing-durations enrichment of the
WorkedCase corpus **including a documented miss** (survivorship-bias guard).
Deterministic-first, every number traceable, framed as *an analysis entry point,
not a signal*.

**What + why (files created / changed):**

- **`services/valuation_ai.py` (new)** — `assess_potential(inputs, scenario_set,
  profile, *, ticker, corpus, transport, settings)`, extending the
  `thesis_ai`/`scenarios_ai` pattern: injectable transport, bounded rounds
  (`anthropic_max_iterations`), JSON-file cache
  (**`backend/.cache/valuation_ai/`**, keyed on ticker+input+**scenario-set**
  hash+model+profile), lazy SDK/pydantic import, deterministic no-key fallback
  (never raises). Produces a `valuation` block:
  - **`potential`** `{value_pct, range_pct, basis_label}` — anchored to the set's
    weighted EV; the no-key `value_pct == scenario_set.weighted_expected_upside_pct`
    exactly (deterministic contract). `range_pct` = the [min,max] scenario upside
    band. When no scenario is priced → `None` + a labelled gap, never a guess.
  - **`confidence`** `{level, rationale}` — a **deterministic heuristic with the
    amended explicit thresholds**: `< min_key_indicators` (3 for Malik) **or**
    `multiple_history.n == 0` ⇒ **low**; `≥ 5` key indicators **AND** `n ≥ 4` ⇒
    **high**; everything between (3–4, or ≥5 with n<4) ⇒ **medium**. The
    number-bearing facts (the counts + the level) stay sourced; the AI may only
    reword the rationale. Verified at all three levels in tests.
  - **`what_would_change`** `[{id,text,why}]` — the thesis `verify_next` gaps
    (catalyst, backlog, management, …) **+** the scenario reversion assumption;
    never empty while the strategy carries verify-gaps. An invented gap id from
    the model is ignored, and no deterministic gap is silently dropped.
  - **Fabrication guard** — prose numbers ⊆ `input_numbers ∪ scenario_numbers ∪
    corpus_numbers ∪ engine_valuation_numbers` (the last = this valuation's own
    computed coverage counts + potential value/range, mirroring WP3b's
    `engine_scenario_numbers`). A stray figure rejects the round → last-valid /
    deterministic fallback. Model literal stays `'claude-sonnet-5'`.
- **`services/thesis.py`** — new public `count_computable_key_indicators(inputs,
  profile)` delegating to the existing `_collect_signals` (the single source of
  the `computable` count), so the confidence heuristic reads coverage from the
  SAME number the entry gate uses — **no recompute / no divergence** (PLAN
  non-goal). Additive; `test_thesis.py` still 13/13.
- **`services/strategies/cases.py`** — WorkedCase corpus enriched with real,
  **sourced** figures, each number living only in the `sources` dict / `citation`
  / `as_of` / `gaps` (never in the reconstructed fundamentals, which stay all
  `MissingData` — zero bare numbers). New `outcome` field ("hit"/"miss"/"").
  Corpus is now **DGN (hit)** — "+2500% w ciągu 5 lat" (≈60 mies. from POS
  02.2023) [DGN]; **OPTEX (entry-pattern)** — sourced entry multiples C/Z ~12,
  prognoza <10, rosnący backlog, po spadku kursu [F][M1; strategy-malik.md
  zasada 8]; **Suntech (documented MISS)** — thesis catalyst (nowe znaczące
  kontrakty) never materialised, held against his own discipline
  ("samousprawiedliwianie błędnych decyzji") [F; M1 §7], entry ~2,40 zł [F];
  **SNT (unverified placeholder)**, kept. What is **not** sourced (DGN's "~20
  PLN", every entry multiple/own-history) stays a labelled gap deferred to
  `scripts/validate_thesis.py` on a machine with egress — **no invented history**.
  The **PEP 562 lazy `CORPUS`** (`__getattr__`) + the circular-import guard
  (thesis→strategies→cases→thesis) are preserved; the enriched numbers land in
  the WP3b/WP4a allowed-set via the untouched `scenarios_ai.collect_corpus_numbers`
  (reads `sources`/`gaps`/`citation`), so `test_thesis_ai.py` stays **17/17**.
- **`services/dossier.py`** — calls `valuation_ai.assess_potential(scenario_inputs,
  scenarios_block, malik.MALIK, ticker=…)` after the scenarios → new dossier
  **`valuation`** block (pass-through with no key).
- **`api/schemas.py`** — `ValuationPotentialOut`/`ValuationConfidenceOut`/
  `WhatWouldChangeOut`/`ValuationOut`, nested `valuation: ValuationOut` in
  `DossierOut` (required backend-side; the deterministic dict shape matches the
  schema field-by-field, verified in-session).
- **Frontend** — `lib/types.ts` gains `Valuation` (+ nested), `Dossier.valuation?`
  **optional** (mirrors the `scenarios?` graceful-degradation pattern);
  `ScenariosPanel.tsx` renders the valuation inside the scenarios card below the
  weighted-EV strip (potential %/range, confidence badge + rationale, "co
  zmieniłoby ocenę" list, framing, engine chip), all numeric fields through the
  `lib/format.ts` pl-PL helpers (`fmtPct`/`signClass`) — **no raw
  `toFixed`/`toLocaleString`/`Intl` literal in the component** (grep-clean);
  `stock/[ticker]/page.tsx` passes `dossier.valuation`; `styles/globals.scss`
  adds a small `.scenarios .valuation` block (reuses the scenarios-scoped
  `.thesis-title`/`.scenario-metrics`/`.framing`/`.ai-note`). `tsc --noEmit` exits
  0. One shared disclaimer covers the scenarios+valuation card (identical
  `DISCLAIMER` — not double-rendered).
- **`scripts/scenarios_smoke.py`** — extended to also print the valuation block
  (engine, iterations, potential %/range, confidence level+rationale,
  what-would-change, narrative). Deferred real-key runbook:
  `cd backend && ANTHROPIC_API_KEY=… python scripts/scenarios_smoke.py SNT`.

**Tests (new + regression, in-session):**

- **`tests/test_valuation_ai.py` (new) — 25/25** in-session (bare Python
  `__main__` runner, no PyPI): confidence heuristic at **all three levels**
  (low via <3 computable, low via n==0, medium at 3–4, medium at ≥5 with n<4,
  high at ≥5 & n≥4); no-key fallback (`potential == weighted upside`); happy-path
  merge (`engine=="ai"`); malformed/transport-error fallback; iteration cap;
  convergence; cache hit + cache-disabled; fabrication guard (stray 888,8
  rejected; scenario `35` + injected-corpus `7,3` allowed); framing + DISCLAIMER
  preserved; invented what-would-change id ignored; **corpus integrity** — lazy
  + import-pure `CORPUS`, ≥1 documented miss, every number sourced (no bare
  fundamental), enriched multiples/durations citable (2500/60/12/10/2,4),
  `evaluate_case` runs on all four.
- **Regression (no WP3 baseline drop):** `test_thesis.py` 13/13, `test_thesis_ai.py`
  **17/17** (corpus enrichment did not break it), `test_scenarios.py` 13/13,
  `test_scenarios_ai.py` 14/14. `python -m py_compile` green over all 41 backend
  `*.py`. `tsc --noEmit` exits 0.
- **Verified green in-session (established `/tmp` pytest shim, same
  technique as the TH/WP2 verifiers):** `test_metrics`/`test_insights`/
  `test_forecast` + `test_biznesradar_parser`/`test_http`/`test_stooq`/
  `test_forum`/`test_yahoo` — that subset **93 passed / 6 skipped**; full
  in-session suite **175 passed / 6 skipped / 0 failed**. Genuinely deferred
  to the user's machine only: the DB/API suite
  (`test_api_phase1`/`test_api_phase3`/`test_migrations`/`test_refresh_prices`,
  plus the client/DB-dependent parts of `test_forum`/`test_yahoo`),
  `npm run build`, and the real-key `ANTHROPIC_API_KEY` smoke.

**Decisions / deviations:**

- **Enriched numbers encoded in the `sources`/`gaps`/`citation` channels** (not a
  new typed numeric field) so `scenarios_ai.collect_corpus_numbers` folds them in
  **without touching WP3 code** — the handoff's "enriched CORPUS becomes citable
  automatically" holds literally. The only structured addition is the digit-free
  `outcome` tag.
- **Suntech is a thesis/catalyst miss, not a multiple-derating miss** — recorded
  honestly (the sources document the catalyst failing + a discipline error, not a
  cheap-multiple slide). It still serves the survivorship-bias guard; the
  distinction is stated in the case's `gaps`.
- **`engine_valuation_numbers` added to the allowed-set** (beyond the plan's
  literal `inputs ∪ scenarios ∪ corpus`) so the deterministic coverage counts the
  rationale must quote are traceable — the exact WP3b precedent
  (`engine_scenario_numbers`); the honesty rule "a deterministic computation from
  those inputs is traceable" governs.

## 2026-07-08 · Scenario simulation engine (WP3 / SC.3)

The stage's main feature: per stock, a coherent **negative / base / positive**
trio of multiple-reversion scenarios + an optional Claude-API refiner, surfaced
next to `ThesisPanel`. Deterministic-first (no key ⇒ traceable fallback), every
number traceable, framed as *an analysis entry point, not a signal*.

**What + why (files created / changed):**

- **`services/scenarios.py` (new, pure)** — the deterministic projector.
  `build_scenario_set(inputs, profile)` selects the sector multiple
  (`select_valuation_multiple`: C/Z generally, **C/WK** finance/realestate,
  **EV/EBITDA** energy — derived from `malik.py` applicability, *no* second copy
  of the sector map), reverts it toward the company's OWN-history quartiles
  (Q1/median/Q3) and computes target price, implied upside, horizon and the
  set-level probability-weighted EV. Probabilities **0.25/0.50/0.25 = 1.00 by
  construction**. Target math per doctrine: C/Z `pe×eps`, C/WK `pwk×bvps`
  (`bvps = equity_tys×1000/shares`), EV/EBITDA `(mult×ebitda_tys×1000 −
  net_debt)/shares` (`net_debt = −net_cash`). **Missing driver ⇒ labelled gap +
  `None` target, never a guessed price** (C/Z fallback when a sector driver is
  absent; if C/Z too is unavailable → `None` + a verify-note). Imports only
  `thesis`/`strategies`/stdlib (deliberately **not** `thesis_ai`), so it runs
  under the bare sandbox Python; carries its own fabrication-guard number
  vocabulary (`input_numbers`/`computed_numbers`/`prose_numbers`).
- **`services/scenarios_ai.py` (new)** — the refiner, extending the
  `thesis_ai.py` pattern: injectable transport, bounded rounds
  (`anthropic_max_iterations`), JSON-file cache (`backend/.cache/scenarios_ai/`),
  lazy SDK/pydantic import, deterministic no-key fallback (never raises). The
  model may reword narratives, adjust probabilities and **add event scenarios**
  grounded in the dossier's `verify_next` gaps; **coherence (Σ=1) is re-imposed
  by us** (renormalise every round). **Widened fabrication allowed-set**:
  `input_numbers ∪ corpus_numbers ∪ engine_scenario_numbers` (sourced inputs ∪
  cited corpus ∪ deterministic-computed) — a stray prose figure rejects the
  round. Model literal stays `'claude-sonnet-5'`.
- **`services/thesis_ai.py`** — three single-line **public aliases**
  (`numbers`/`extract_json`/`parse_response`) so the refiner reuses the helpers
  without reaching into privates. No behaviour change (`test_thesis_ai.py` still
  17/17).
- **`services/metrics.py`** — generalised `compute_pe_history` → new
  `compute_multiple_history(values, current)` returning `{median,q1,q3,current,
  percentile,**n**}` (works for any multiple series). `PeHistoryStats` kept as an
  alias of the new `MultipleHistoryStats`; `compute_pe_history` kept as a thin
  alias — every existing C/Z call site unchanged. **Decision:** `n` flows onto
  the `pe_history` dict; `PeHistoryOut` left untouched (pydantic drops the extra
  key) to keep the deferred DB/API leg's blast-radius zero.
- **`services/dossier.py`** — builds `ScenarioInputs`, calls
  `build_scenario_set` then `simulate_scenarios` → new dossier **`scenarios`**
  block. Loads the selected multiple's own-history series (parametrised by
  indicator code, same query shape as `cz`). **`ebitda_ttm=None` (labelled gap):
  EBITDA TTM is not computed anywhere yet**, so energy names fall back to their
  own C/Z history rather than fabricate an EV/EBITDA (the math is implemented +
  unit-tested via direct inputs; WP-later can feed real EBITDA).
- **`api/schemas.py`** — `ScenarioTargetMultipleOut`/`ScenarioHorizonOut`/
  `ScenarioOut`/`ScenarioSetOut`, nested `scenarios: ScenarioSetOut` in
  `DossierOut`.
- **Frontend** — `components/ScenariosPanel.tsx` (Overview order
  MetricCards → Teza → **Scenariusze** → Analiza → Prescore → Kurs), mirrors
  `ThesisPanel` incl. the `silnik` engine chip + disclaimer + the "punkt wejścia
  w analizę, nie sygnał" framing; degrades when `scenarios` is absent. Values go
  through `lib/format.ts` pl-PL helpers (`fmtPln`/`fmtPct`) — **no
  `toFixed`/`toLocaleString`/`Intl` literal in the panel** (grep-clean),
  reconciling "use pl-PL helpers" with the plan's as-is grep rule. `lib/types.ts`
  gains `Scenario`/`ScenarioSet` (field-by-field) + optional `Dossier.scenarios`.
  `globals.scss` self-contained `.scenarios` card. `tsc --noEmit` exits 0.
- **`scripts/scenarios_smoke.py` (new)** — deferred real-key runbook mirroring
  `thesis_ai_smoke.py`: prints engine, iterations, the scenario set + weighted EV.

**Tests (in-session, bare `python3` + `/tmp` pytest shim):**

- `tests/test_scenarios.py` **13/13** — hand-checked targets/upsides/weighted-EV
  for C/Z, C/WK and EV/EBITDA (computation shown in comments), multiple-selection
  by sector, probability Σ=1, neg≤base≤pos ordering, `missing_driver_labels_gap`
  (None target, no invented number), C/Z fallback, and `every_scenario_number_is_
  traceable` (prose ⊆ inputs ∪ computed).
- `tests/test_scenarios_ai.py` **14/14** — happy-path AI merge, malformed
  fallback, iteration-limit, convergence, fabrication guard (stray rejected),
  corpus-number allowed, engine-number allowed, probability renormalisation after
  an added event scenario (`|Σ−1|≤0.01`), no-key fallback, cache hit/skip +
  disabled bypass, framing+DISCLAIMER preserved.
- **No regression:** the stage-TH/WP2 baseline **123 passed** is reproduced green
  (test_thesis 13, test_thesis_ai 17, test_metrics 20, test_insights 15,
  test_forecast 5, test_biznesradar_parser 33 (+6 skip), test_http 6, test_stooq
  8, test_forum 3, test_yahoo 3); + the 27 new = **150 passed in-session**.
  (`test_forum 3` / `test_yahoo 3` are the **pure subsets** — 3-of-6 and 3-of-5;
  the skipped remainder needs the deferred DB/client fixture.)
  `py_compile` green over all 40 `backend/**/*.py`; `tsc --noEmit` exits 0.

**Deferred to the user's machine (documented, not run in-session — no PyPI /
egress / DB):** `cd backend && pytest` (full DB/API); `cd frontend && npm run
build`; `ANTHROPIC_API_KEY=… python scripts/scenarios_smoke.py <TICKER>` (real
refinement). Learning note (`docs/learning/phase-scenarios.md`) is a **WP5**
deliverable — hook recorded here per WP3 acceptance #7.

**Decisions / deviations:** (1) `scenarios.py` keeps its **own** number-extraction
vocabulary rather than importing `thesis_ai` — module purity (the acceptance
import allow-list) beats DRY here; the refiner still reuses `thesis_ai`'s
transport/parse/cache. (2) AI event scenarios carry **no** target price/upside
(a catalyst's magnitude isn't computed) and the default horizon band — honest
until WP4's corpus supplies real repricing durations. (3) The fabrication guard
checks **prose** numbers ⊆ allowed; structured numbers are engine-controlled
(kept-deterministic or our renormalised probabilities / recomputed weighted EV),
matching "deterministic-computed scenario numbers" in the allowed-set.
(4) **Plan doc amended** (`docs/plan-stage-scenarios.md` WP3c text + acceptance
#6 + the verifier/protocol restatements) so spec matches code: the "render
as-is / same rule as `ThesisPanel`" wording is corrected to **permit the
`lib/format.ts` pl-PL helpers for numeric fields** — `ThesisPanel` renders only
backend prose, but `ScenariosPanel` renders raw numbers (target
price/upside/probability/weighted EV) that must format pl-PL like `MetricCards`
(CLAUDE.md); the grep still bars raw `toFixed`/`toLocaleString`/`Intl` literals
in the component.

---

## 2026-07-08 · Clean project: remove provably-dead code (WP2 / SC.2)

Conservative dead-code sweep before the scenario engine lands — prove-before-delete,
green tests as the safety proof. The codebase was already clean (an `ast` unused-import
scan over `backend/app` + `backend/scripts` reported **zero** unused imports/names both
before and after), so the removals are small; the bulk of the WP is the *proof* that it
is clean. **No files moved/renamed/merged (0 structural changes)**; no frontend source
touched; the "do NOT touch" list respected (all byte-unchanged).

**Removal ledger** (path · why dead · proof — nothing removed without a green proof):

| # | Path | What / why dead | Proof |
|---|------|-----------------|-------|
| 1 | `backend/app/services/forecast.py` | fn `_last_quarters(income, count)` — superseded: `default_assumptions` and `compute_forecast` both inline `sort_periods(income.keys())[-n:]` and never call it | `grep -rn "_last_quarters" backend/ --include='*.py'` → **only its own def line**; zero references in-file or repo-wide (frontend/docs/tests incl.). Removed the 2-line fn (−4 lines w/ spacing). No import left orphaned (`IncomeSeries`/`sort_periods`/`next_period`/`previous_year_period` all still used; strict re-scan of the file = 0). |
| 2 | `backend/tests/test_biznesradar_parser.py` | unused imports `date`, `ParseError`, `page_url`, `parse_price_history` — imported but referenced by no test in the file | per-name word-boundary `grep` across all 303 lines → each appears **only on its import line**; these names occur repo-wide in tests **only** in this file (only as imports). The symbols stay live in `app/scrapers/biznesradar.py` and elsewhere — only the redundant local bindings dropped (−4 lines). Post-edit strict `ast` scan of `backend/tests` = **0** candidates. |

Tool: a stdlib-`ast` unused-import scanner (no PyPI; `ruff`/`pyflakes` are the equivalent
on the user's machine), cross-checked by word-boundary `grep` per candidate.

**Deliberately KEPT (borderline — recorded so the choice is auditable):**
- **Frontend unused exports** — `fmtTys` (`src/lib/format.ts`), `getIndicators` + `getDividends`
  (`src/lib/api.ts`) are currently unreferenced, but they are coherent **library surfaces**,
  not orphaned files/modules: `api.ts` is a one-wrapper-per-endpoint client and those two
  mirror the **live** FastAPI routes `GET /companies/{t}/indicators` + `/dividends`; `fmtTys`
  is one primitive in the format-helper family. Pruning a library surface is the kind of
  gratuitous restructuring the WP forbids, doubly so with the frontend mid-Stage-TH
  (uncommitted). `tsc --noEmit` has no `noUnusedLocals`, so this is not a compile gate.
- `strategies/__init__.py` `base`/`cases` — a naive scan flags them, but they are legitimate
  `__all__` package re-exports (the `__all__`-aware scan correctly reports them used).
- `Criterion.thresholds` (`strategies/base.py`) — documented **PLAN §10 extension point**
  ("unused by the verdict-based engine today, kept so the data shape is ready"), not dead.
- Gitignored artifacts (`__pycache__/`, `.DS_Store`, `.next/**/*.old`) — not source; out of scope.
- The protected set — `stooq.py`/`yahoo.py` (live price-chain legs), `live-20260708/` evidence
  fixtures, `record_fixtures.py`/`record_topic_fixture.py`, `thesis_ai_smoke.py`/`validate_thesis.py`,
  `skills/scraper-doctor/SKILL.md` — all confirmed **byte-unchanged**. The dividend-layer gap
  (`docs/validation-thesis.md`) is a user product decision — **not** touched.

**Safety proof (in-session; counts re-run AFTER cleanup):**
- **`py_compile` green: 53/53** (`app`+`tests`+`scripts`, the Stage-TH baseline set) and
  **58/58** whole backend incl. `alembic`. No files removed ⇒ counts unchanged.
- **In-session test suite: 123 passed / 0 failed** (bare `python3` for the two `__main__`
  runners + a minimal `pytest` shim built in `/tmp`, repo untouched — same technique as the
  TH verifier). Per file: `test_thesis` 13, `test_thesis_ai` 17, `test_metrics` 20,
  `test_insights` 15, `test_forecast` **5**, `test_biznesradar_parser` **33 (+6 skip)**,
  `test_http` 6, `test_stooq` 8, `test_forum` 3 (+3 skip), `test_yahoo` 3 (+2 skip) — identical
  to the TH baseline; the two touched files (`test_forecast`, `test_biznesradar_parser`) stay
  green. In-file skips 11; the DB/API files (`test_api_phase1` 12, `test_api_phase3` 6,
  `test_migrations` 1, `test_refresh_prices` 5 = 24) are **collection-skipped** in-session
  (import sqlalchemy/fastapi at top) — deferred to the user machine. (The "123 passed, 29
  skipped" TH figure: the **123 passes are identical**; only the deferred-file skip tally
  differs by counting method — my harness AST-counts 24 deferred tests vs pytest's 18-ish —
  no pass lost, no fail.)
- **`tsc --noEmit` exit 0** (no frontend change).
- **Unused-import `ast` scan over `backend/app` + `backend/scripts`: ZERO** (acceptance #6);
  **0 structural moves** (acceptance #6 trivially met).

**Deferred (documented, not run in-session):** `cd backend && pytest` (full DB/API suite +
real fixtures) on the user's machine confirms no import broke — the 24 collection-skipped
tests are the leg that exercises the edited modules through the DB/API path.

Why / decisions:
- **Prove-before-delete + conservatism win over volume.** The plan anticipates a small (even
  empty) cleanup; the deliverable's value is the zero-unused proof + no-orphans finding as much
  as the two removals. Everything ambiguous (unused *library* exports, extension-point fields)
  was **kept and ledgered**, not guessed-away.
- **`git diff` note for the verifier:** the WP2 *code* delta is exactly `forecast.py` (−4) +
  `test_biznesradar_parser.py` (−4). Every other modified/untracked path in the tree
  (`schemas.py`, `config.py`, `dossier.py`, `.env.example`, `types.ts`, `page.tsx`,
  `globals.scss`, `tsconfig.tsbuildinfo`, the `strategies/`, `thesis*.py`, docs, …) is
  **pre-existing uncommitted Stage-TH work**, unchanged here (Stage TH is entirely uncommitted).
  Refs SC.2.

## 2026-07-08 · Memory: compact context for stage SC (WP1 / SC.1)

Re-consolidated project memory **before** any scenario code lands, so the new
work starts from a small always-loaded core. **Docs-only — no code/schema/config
touched;** `skills/scraper-doctor/SKILL.md` (quirks ledger) left **byte-for-byte
unchanged**.

- **CLAUDE.md (66 → 69 lines, ≤70 budget held).** The "Read on demand" index now
  lists `docs/plan-stage-scenarios.md` (+ the WP5-added
  `docs/validation-scenarios.md` / `docs/learning/phase-scenarios.md`); the
  changelog-archive pointer generalised to `docs/changelog-archive-*.md` (build
  day 07-07 + Stage TH 07-08); `docs/strategy-malik.md` relabelled as the spec
  the thesis **+ scenario** engines implement (scenarios reuse the same
  valuation doctrine).
- **Changelog archive.** The closed Stage-TH block — the six TH.* build entries
  (TH.1–TH.5, incl. TH.2b), the WP4b live-run note, the WP4 sandbox-rescope note,
  and the three Stage-TH plan entries, i.e. the whole contiguous 2026-07-08 TH
  section (~524 lines) — moved **verbatim** into the new
  `docs/changelog-archive-thesis-2026-07-08.md` (byte-identical, only relocated;
  mirrors the `docs/changelog-archive-2026-07-07.md` pattern: header pointing
  back to CHANGELOG + quirks ledger, then the entries). Left in `CHANGELOG.md`:
  both digests (Stage TH + build day), the most recent post-stage verification
  entry, and the current SC-plan entry — the always-loaded file drops from 841
  lines to the digests-plus-recent core. The top archive pointer and the
  Stage-TH digest cross-reference now name the new archive.
- **TASKS.md.** The **Stage SC** section (SC.1–SC.5) was already added by the
  SC-plan step; left as-is with every box **unticked** (ticked only after each
  WP's verifier PASS).

Why / decisions:
- **Compaction goal over the literal enumeration.** The plan lists "the six TH.*
  build entries + the WP4b/rescope entries"; I additionally moved the three
  Stage-TH *plan* entries so the live `CHANGELOG.md` keeps **only** the two
  digests + the post-stage verification of Stage TH (the deliverable's "leave in
  CHANGELOG.md" end-state) and the whole contiguous TH section relocates as one
  block — matching the 2026-07-07 precedent. No changelog content is lost (every
  moved entry is findable in the archive); acceptance #2 (digests + pointer
  retained) still holds.
- **Quirks ledger sacrosanct.** `skills/scraper-doctor/SKILL.md` untouched
  (`git diff` empty; md5 unchanged) — its knowledge survives compaction intact.

In-session regression (WP1 changed no code, so behaviour cannot move):
`test_thesis.py` **13/13** + `test_thesis_ai.py` **17/17** green under bare
`python3`; `test_metrics.py` **20/20** + `test_insights.py` **15/15** green under
the minimal pytest shim (built in `/tmp`, repo untouched). The git working tree
already carried the uncommitted Stage-TH files (untracked + modified `.py`/`.ts`);
the WP1 delta on top of that is **`.md`-only** (`CLAUDE.md`, `CHANGELOG.md`, the
new archive). Full `pytest`/DB path unchanged — still the user-machine leg. Refs
SC.1.

## 2026-07-08 · Plan: scenario-simulation stage (stage SC, SC.1–SC.5)

Planning-only change (no code). Added `docs/plan-stage-scenarios.md` — the stage
that answers the user's "single-scenario output is unhelpful": per stock a small
set of **negative/base/positive + event scenarios**, each with a coherent
probability (Σ≈1), a data-grounded narrative, a **target valuation from the
sector-relevant multiple** (C/Z generally, C/WK for banks/deweloperzy, EV/EBITDA
for surowce/energetyka) read against the company's **own** multiple history
*only* (*"a nie tylko do rynku czy branży"*), a repricing horizon, implied
upside, and a set-level probability-weighted EV vs current price. The worked-case
corpus feeds the repricing horizon, the AI's probability/timing sanity-check and
WP4's confidence — not the target number. Plus an **AI valuation agent** that
consumes all data + the scenarios → stock-potential + confidence + "what would
change the assessment". Also added `TASKS.md` **Stage SC** (SC.1–SC.5, unticked).

Why / decisions:
- **Extends the TH.2b pattern, deterministic-first.** `services/scenarios_ai.py`
  + `services/valuation_ai.py` reuse `thesis_ai.py`'s injectable transport,
  JSON-file cache, and fabrication guard behind a **no-key fallback** (engine:
  deterministic|ai). The deterministic core `services/scenarios.py` is a pure
  function layer (own-multiple reversion off `metrics.compute_pe_history`
  generalised to any multiple) that always yields a coherent set — the AI is
  never on the critical path. Not a stochastic Monte-Carlo (documented
  non-goal); discrete scenarios, simple-first.
- **Wider-but-still-closed fabrication guard.** Unlike the thesis (which only
  reuses insight numbers), scenarios legitimately *compute* new numbers (target
  price, upside, EV, probabilities, horizons). So the allowed-set is
  `inputs ∪ deterministic-computed scenario numbers ∪ cited worked-case corpus
  numbers` — every figure traceable to fetched data, a labelled assumption, a
  deterministic computation, or a cited comparable. Missing per-share driver
  (EBITDA TTM / book value) → labelled gap + `None` target, never a guess.
- **Corpus enrichment feeds evidence.** WP4 adds real, sourced multiples +
  repricing durations to the WorkedCase corpus **incl. ≥1 documented miss**
  (survivorship-bias guard), so horizons and confidence cite comparables. Lazy
  `CORPUS` (PEP 562) + import purity preserved; DGN "~20 PLN" stays
  UNVERIFIED/unused.
- **Housekeeping WPs first.** WP1 compacts memory (CLAUDE.md index + archive the
  closed Stage-TH changelog entries into a new
  `docs/changelog-archive-thesis-2026-07-08.md`, quirks ledger left byte-identical);
  WP2 removes provably-dead code with a per-item zero-reference grep proof and
  the full test suite green as the safety proof.
- **Sandbox honesty carried over:** no PyPI/egress in-session → pure layers +
  stub-transport tests run in-session, DB/API/`npm build`/real-key smoke/live BR
  deferred to the user's machine with exact runbook commands. Per-WP
  fresh-context verifier (sonnet) against this plan; implementation = opus.
- **P5 reconciliation:** scenarios_ai/valuation_ai transports are reused by
  P5.4; the Phase-5 analysis product (skill/analyses/AI tab) stays separate.
  Learning note `docs/learning/phase-scenarios.md` lands in WP5.

## 2026-07-08 · docs/validation: fresh-context verification pass + dividend-row correction (TH post-stage)

Independent fresh-context verification of the just-closed Stage TH (sonnet
agents, hands-on). **Docs-only change — no code, test, or strategy-data file
touched.** One documentation defect found and fixed; two cosmetic nits recorded;
one pre-existing layer gap surfaced for a user product decision. `test_thesis.py`
**13/13** + `test_thesis_ai.py` **17/17** re-confirmed.

**Verified green (exact counts).** `py_compile` **53/53** files green; import
purity holds (no pydantic/anthropic/fastapi/sqlalchemy/requests after importing
thesis/thesis_ai/strategies), `cases.CORPUS` lazy-builds DGN+SNT with no circular
import. Beyond the documented bare-`python3` runbook, a minimal **pytest shim**
(fixture/parametrize/raises/approx + faked pure conftest helpers, built in `/tmp`,
repo untouched) ran the pure suites in-sandbox too: `test_metrics` 20/20,
`test_insights` 15/15, `test_forecast` 5/5, `test_biznesradar_parser` 33 + 6 skip
(genuine — `real_br_*.html` never recorded), `test_http` 6/6, `test_stooq` 8/8,
`test_forum` 3 + 3 skip, `test_yahoo` 3 + 2 skip → **123 passed, 0 failed, 29
attributed skips**. Only `test_migrations.py` + `test_refresh_prices.py` (import
sqlalchemy at top) and the API/DB fixtures truly need the user machine. This
CORRECTS the "Stage TH complete" entry's line that `test_insights`/`test_metrics`
"cannot run" in-session (a bracketed correction note was added inside that entry).

**Defect found + fixed (the point of the pass).** The E2E replay — the unmodified
`scripts/validate_thesis.py` functions over the on-disk DEC cache (byte-identical
to the committed fixtures) — reproduces **23 of 24** documented numbers exactly.
The one miss was a real doc defect: `docs/validation-thesis.md` "silnik ↔ strona"
table carried a `Dywidenda | 3 lata z rzędu, stopa 4,9% | … | 0` row implying the
**thesis engine** judges dividend for DEC. **False** — the live DEC thesis output
has no dividend entry anywhere (`insights.missing == ["pe_vs_history"]` only).
Root cause (pinned by running the code): `insights.py`
`_GROUP_PLAYBOOK["industrial"]` has no `"dividend"` (only finance/energy/realestate
groups do), so `spec_dividend()` never runs for DEC (sector "Materiały budowlane" →
industrial), `idx.get("dividend")` is `None` in `build_thesis`, and the criterion
is silently skipped. The dividend **data** parses correctly (2023–2025, DPS
1,20 zł, 4,9% — matches the page); the gap is purely indicator selection. Fix:
the engine cell now reads "wskaźnik nieoceniany przez tezę dla grupy `industrial`"
with an explanatory note under the table. Fabrication guard on the live output:
**32** input numbers vs **9** read numbers, **0** invented. `evaluate_case`: DGN
"0/4" + SNT "0/2" → `insufficient_data`, `matches=True`.

**Layer gap left to the user (product decision, not a bug to fix now).**
`strategies/malik.py`'s `dividend` Criterion has no sector-applicability
restriction, while the insights playbook excludes dividend for **5 of 8** sector
groups → a real dividend history is invisible to the thesis engine (no pro, no
con, no `verify_next` flag) for industrial/tech/biotech/consumer/other companies.
This is **pre-existing `insights.py` behavior, not introduced by Stage TH**.
Whether to add dividend to more playbooks, restrict the malik criterion, or route
never-selected criteria to `verify_next` is left to the user — recorded in the
validation doc, no code change here.

**Two cosmetic nits recorded (out-of-scope, user decision).** (1) already-flagged
`insights.py` "+1.8 p.p."/"+1,8 p.p." pl-PL punctuation mismatch; (2) new —
`malik.py`'s `size_pro_text` hardcodes "Mała spółka ({size})", so a small-cap pro
renders "Mała spółka (Mała spółka) — sweet spot…" (duplication; micro reads fine).
Both need their own test + CHANGELOG entry; neither touched here.

**Other checks + politeness.** No-key fallback returns exactly
`build_thesis().to_dict()` + `engine:"deterministic"` (no `ai_notes`, no cache dir
created). `classify_size` sanity on real numbers: SNT reported mcap 3 213 775 722
→ **mid**; **one** polite live `web_fetch` of
`https://www.biznesradar.pl/notowania/PKNORLEN` (200, redirect →`/notowania/ORLEN`,
markdown) → hand-read "Kapitalizacja: 159 977 814 352" → **large** (size factor
flips PRO→CON; small=attractive/mid=neutral/large=neutral). Frontend `tsc
--noEmit` strict whole-app exit 0 (TypeScript 5.9.3, 28 files); `types.ts` ↔
`ThesisOut` field-by-field; `ThesisPanel` degraded states/chips/disclaimer/order
verified. **Politeness: 1 live request total this session, 0 retries, archiwum
untouched, 0 pagination, SNT not re-fetched.**

**Unchanged user-machine runbook** (still deferred — needs PyPI / a DB / npm / a
real key / egress): `cd backend && pytest` (full DB/API suite);
`scripts/validate_thesis.py DGN SNT DEC <large-cap>` (live ≥4-ticker cross-check);
`ANTHROPIC_API_KEY=… python scripts/thesis_ai_smoke.py SNT` (one real refinement).
No Alembic migration this change (latest remains 0004). Refs TH.4.

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

## 2026-07-08 · Stage TH digest — investment-thesis layer

Decisions that govern the thesis layer (full per-WP detail archived in
`docs/changelog-archive-thesis-2026-07-08.md`):

- **Strategy = data, engine = generic:** a strategy is a `StrategyProfile`
  (frozen dataclasses in `services/strategies/`), the engine `thesis.py` is
  strategy-agnostic — no `if strategy == "malik"` anywhere; genericity is
  unit-tested with a toy profile. New investors = new profile modules, zero
  engine change (PLAN §10).
- **Reuse, don't recompute:** `thesis.py` consumes `insights.py` verdicts and
  never re-derives a number, so the UI can't show two values for one metric; a
  fabrication guard (shared by the deterministic and AI paths) forbids any read
  number absent from the inputs — missing indicators route to `verify_next`.
- **Deterministic-first AI (TH.2b):** `thesis_ai.py` refines the read via an
  injectable Claude transport behind a **no-key fallback** (`engine:
  deterministic|ai`); the model may reword/re-pick but weights, principle tags,
  label and disclaimer are re-imposed by us. Its transport/config/cache are
  reused by P5.4 — but the Phase-5 analysis product (`skill/`, `analyses`, AI
  tab) stays separate.
- **Honesty over a backtest:** DGN/SNT are stored as thin `WorkedCase`s with
  explicit gaps (no fabricated historical figures); the live ≥4-ticker
  cross-check is deferred to the user's machine (`scripts/validate_thesis.py`),
  never papered over. Not investment advice — entry-quality is an analysis
  entrance, never a signal.
- **Extensibility staged, not built:** WorkedCase corpus + `evaluate_case` +
  profiles-as-data make the calibration/other-investor-strategies stage a
  data exercise (new profile *versions*), not engine surgery — deliberately
  deferred this stage.
