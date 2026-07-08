# Stage plan — Scenario simulation engine (stage SC)

**Status:** planned 2026-07-08. Owner: implementation sessions per WP.
**Read alongside:** `docs/plan-stage-thesis.md` (the stage this builds ON —
same style, same honesty rules, same model split); `docs/strategy-malik.md`
(the valuation doctrine the scenarios must stay faithful to — forward/own-history
multiples, catalyst-as-gap, margin-of-safety trio); PLAN §7 (metrics/frontend),
§8 (AI layer), §10 (extension points), §13 (learning);
`services/thesis_ai.py` (**the pattern WP3/WP4 extend** — injectable transport,
fabrication guard, JSON-file cache, no-key fallback); `services/thesis.py` +
`services/strategies/` (deterministic engine + strategy-as-data the scenarios
reuse); `services/metrics.py` (`compute_pe_history` = own-multiple ranges);
`skills/scraper-doctor/SKILL.md` (authoritative quirks — never re-derived).

## Process & models (binding, carried from stage TH 2026-07-08)

- Planning/orchestration: top-level session. **Implementation agents: opus.**
  **Testing/debugging/verification agents: sonnet** (plan-conformance verifiers
  count as testing).
- Loop per WP: implementation agent (opus) → a **separate fresh-context
  verifier (sonnet)** judging against THIS plan's acceptance criteria
  (deviations, regressions, fabricated numbers, broken tests). Fail → fix →
  re-verify; a WP is done only after a verifier PASS. The stage ends with a
  fresh-context plan-conformance review (WP5).
- The verification protocol + the exact evidence each verifier must collect are
  spelled out per WP ("Verifier checklist") and summarised in
  §"Verification protocol".

## Goal

The current dossier gives **one** thesis read (`entry_quality` + one
`thesis_read`). The user finds a single-scenario output unhelpful. This stage
adds, **per stock, a small set of simulation-based scenarios** — a
**negative / base / positive** trio plus optional **company-specific event
scenarios** — each carrying:

- an **expected probability** (coherent across the set, Σ ≈ 1);
- a **narrative grounded strictly in fetched data** (or a *labelled* assumption
  — never an invented fact);
- a **target valuation** built from the *wskaźniki wyceny that matter for that
  stock's sector* (C/Z generally; **C/WK** for banks/deweloperzy; **EV/EBITDA**
  for surowce/energetyka), read against **historical ranges** = the company's
  **own** multiple history *alone* — the forward multiple against its own past,
  *"a nie tylko do rynku czy branży"* (`docs/strategy-malik.md`). The worked-case
  corpus does **not** set this target number; it informs the repricing horizon
  (next bullet), the AI's probability/timing sanity-check (WP3b) and WP4's
  confidence;
- an **expected timeframe** (repricing horizon) informed by how long comparable
  repricings took in the corpus;
- an **implied price / upside**;
- and a set-level **probability-weighted expected value vs the current price**.

On top of the scenarios, an **AI valuation agent** (WP4) reads all gathered data
**plus the scenarios** and returns a **stock-potential valuation**: how much
potential, at what confidence, and what would change the assessment.

Both new layers **extend the `thesis_ai.py` deterministic-first pattern**: an
injectable Claude transport, bounded iteration, a JSON-file cache, a fabrication
guard, and a **deterministic no-key fallback** so the sandbox (and any keyless
run) always gets a coherent, traceable result. Surfaced in the UI next to
`ThesisPanel`, framed as **an analysis entry point, not a signal**.

## Non-goals (explicit — prevent gold-plating)

- **Not a stochastic Monte-Carlo.** "Simulation" here = a **small set of discrete
  scenario projections** (multiple-reversion paths), not thousands of random
  draws, not a distribution engine, not option-pricing. A real MC sampler is a
  documented future extension (PLAN §10), **not built now**.
- **No buy/sell signal, no price target as advice.** Every scenario is an
  *"if-this-then-that"* projection with a standing not-advice disclaimer
  (`thesis.DISCLAIMER`, reused). Upside numbers are conditional on the stated
  assumption, never a recommendation.
- **No new scraping sources; no new indicators invented.** Scenarios reuse the
  dossier's already-computed pieces + the company's own multiple history (from
  `indicator_values`, already stored). BiznesRadar **archiwum page 1 only**,
  low volume, all HTTP via `scrapers/http.py`; quirks from the ledger, not
  re-derived.
- **No recompute / no divergence from `insights.py`/`thesis.py`.** The scenario
  layer *consumes* their verdicts and numbers; a per-scenario target price is a
  new **computed** number (pure function of sourced inputs), never a restated
  indicator that could disagree with the dossier.
- **No Phase-5 collision.** This is engine-level dossier enrichment
  (`scenarios` + `valuation` blocks). The Phase-5 analysis product (`skill/`,
  `analyses` table, Analiza AI tab, `AI_DAILY_LIMIT`) stays Phase 5. Like
  TH.2b, the transport/config/cache built here are **reused by P5.4**, not
  replaced (see §"Reconciliation").
- **No learning loop / weight tuner this stage.** Enriching the WorkedCase
  corpus (WP4) seeds calibration; the tuner remains a later stage.

## Sandbox / testing reality (state honestly, never paper over)

Verified during stage TH and unchanged:

- **No PyPI in-session.** Pure layers run under the bare system Python.
  `scenarios.py` may import only `insights`/`metrics`/`thesis`/`strategies` +
  stdlib (all third-party-free) so it — and `test_scenarios.py` — run
  in-session. `scenarios_ai.py`/`valuation_ai.py` import the Anthropic SDK and
  pydantic `Settings` **lazily inside functions** (mirror `thesis_ai.py`), so
  they import and stub-test with no PyPI.
- **No network egress from sandbox Python** (proxy 403s CONNECT to every host).
  Live BR fetches are impossible from `app/scrapers/http.py` in-session. The
  agent tool `mcp__workspace__web_fetch` reaches BR but returns **markdown, not
  HTML** (the BeautifulSoup parsers can't use it — proven in
  `docs/validation-thesis.md`). Therefore **live validation is fixture-first**;
  any live probe is optional, ≤ a few requests, politeness replicated by hand,
  **no archiwum pagination**.
- **DB/API layers are compile-checked in-session only** (`python -m py_compile`);
  wiring them needs SQLAlchemy/Pydantic → deferred to the user's machine.
- **Frontend:** `tsc --noEmit` runs in-session (node_modules committed);
  `npm run build` and the live UI are deferred to the user's machine.
- Every WP states which checks are in-session vs deferred. Deferred ≠ skipped —
  it ships as a documented runbook command.

---

## WP1 — Compact context (memory + changelog consolidation)

**Scope.** Re-consolidate project memory so the always-loaded core stays small
and the detail is on-demand — **before** any scenario code lands (so the new
work starts from a clean, cheap context). No behaviour change to code.

**Deliverables.**
- **`CLAUDE.md`** stays the short always-loaded core. Update the "Read on demand"
  index to list the new stage docs: `docs/plan-stage-scenarios.md` and (added by
  WP5) `docs/validation-scenarios.md`, `docs/learning/phase-scenarios.md`.
  Trim/merge any line made stale by stage TH; the always-loaded core stays
  **≤ ~70 lines** (it is 66 today — do not grow it materially).
- **Changelog archive.** `CHANGELOG.md` has grown to ~840 lines. Archive the
  **closed Stage-TH per-WP entries** (the six 2026-07-08 TH.* build entries +
  the WP4b/rescope entries) **verbatim** into a NEW archive file
  `docs/changelog-archive-thesis-2026-07-08.md`, following the existing
  `docs/changelog-archive-2026-07-07.md` pattern (header pointing back to
  CHANGELOG + quirks ledger, then verbatim entries). Leave in `CHANGELOG.md`:
  the two existing **digests** (the "Stage TH digest" + the build-day digest)
  and the most recent post-stage verification entry. Add a one-line pointer in
  `CHANGELOG.md` to the new archive (mirroring the existing archive pointer at
  the top).
- **`TASKS.md`.** Add the **Stage SC** section (tasks `SC.1`–`SC.5`, this plan)
  so sessions can say "do SC.3"; leave all boxes unticked (ticked only after a
  verifier PASS).
- **Quirks ledger is sacrosanct.** `skills/scraper-doctor/SKILL.md` is **not
  touched** in WP1 (its knowledge must survive compaction intact).

**Acceptance (mechanically checkable).**
1. `CLAUDE.md` "Read on demand" index lists `docs/plan-stage-scenarios.md`;
   its always-loaded body is **≤ 70 lines**.
2. `docs/changelog-archive-thesis-2026-07-08.md` exists and contains the
   archived TH.* entries **verbatim** (a diff of moved text shows byte-identical
   bodies, only relocated); `CHANGELOG.md` retains both digests + a pointer to
   the new archive; **no changelog content is lost** (every archived entry is
   findable in the archive).
3. `git diff skills/scraper-doctor/SKILL.md` is **empty** — the quirks ledger is
   byte-for-byte unchanged.
4. `TASKS.md` has a **Stage SC** section with `SC.1`–`SC.5`, all unchecked.
5. In-session regression: the pure test subset (`test_thesis.py` 13,
   `test_thesis_ai.py` 17, `test_metrics.py` 20, `test_insights.py` 15) still
   runs green — WP1 changed **no code** (a `git diff --stat` shows only
   `.md` files changed).
6. A `CHANGELOG.md` entry for WP1 exists (date · scope · what + why).

**Verifier checklist.** Confirm the archive is verbatim (grep a distinctive
sentence from an archived TH entry — it must be in the archive, not the live
file); `git diff --stat` shows only markdown changed and SKILL.md untouched;
CLAUDE.md index updated and ≤ 70 lines; TASKS.md SC section present; re-run the
pure subset green; confirm the WP1 CHANGELOG entry.

---

## WP2 — Clean project (remove dead code, prove safety with green tests)

**Scope.** Identify and remove code that is genuinely **no longer used** (dead
modules, superseded scraper paths, unused imports, orphaned files/fixtures) and
tidy structure for consistency — **conservatively**. Simple first: remove only
what is *provably* unreferenced; do not restructure gratuitously.

**Method (binding).**
- **Prove-before-delete.** For every candidate, record a **removal-ledger row**
  in the WP2 CHANGELOG entry: `path · why dead · proof` where *proof* is a repo
  grep (`Grep`) showing **zero** references outside the file itself (and outside
  archived changelog prose). Nothing is deleted without a green proof.
- **Unused-import scan.** Use a stdlib-`ast` scan (no PyPI needed) — or `ruff`/
  `pyflakes` on the user's machine — over `backend/app/` and `backend/scripts/`
  to list unused imports/names; remove the confirmed ones. Record the tool used.
- **Do NOT touch (known live, easy to misjudge):** `stooq.py`/`yahoo.py` (both
  are live legs of the price chain — quirks ledger "Price chain"); the
  `live-20260708/` evidence fixtures (referenced by `docs/validation-thesis.md`
  — moving/removing them needs the user's call, out of scope here);
  `record_fixtures.py`/`record_topic_fixture.py` (scraper-doctor step 4);
  `thesis_ai_smoke.py`/`validate_thesis.py` (deferred user-machine runbooks).
  The **dividend layer gap** flagged in `docs/validation-thesis.md` is a
  **product decision left to the user** — WP2 does **not** silently change it.
- **Safety proof = the full runnable test suite stays green after cleanup.**
  In-session that means the pure + pytest-shim subset at **the same counts**
  (baseline below); the full DB/API `pytest` is the deferred user-machine leg.

**Acceptance (mechanically checkable).**
1. Every removed path has a removal-ledger row (path · why · zero-reference grep
   proof) in the WP2 CHANGELOG entry. **No item removed without a proof.**
2. In-session test subset is green at **≥ the stage-TH baseline**:
   `test_thesis.py` 13/13, `test_thesis_ai.py` 17/17, `test_metrics.py` 20/20,
   `test_insights.py` 15/15, `test_forecast.py` 5/5,
   `test_biznesradar_parser.py` 33 (+6 skip), `test_http.py` 6/6,
   `test_stooq.py` 8/8 — i.e. the "123 passed, 29 skipped" figure holds (or the
   delta is explained by an intentionally-removed test with its ledger row).
3. `python -m py_compile` is green over every remaining `backend/**/*.py`
   (report the file count; it may drop from 53 if files were removed — the drop
   equals the removal-ledger count).
4. Frontend `tsc --noEmit` exits 0 (unused frontend files/imports, if any, are
   ledgered the same way).
5. **Nothing still referenced was deleted** — the verifier independently
   re-greps a sample of removed names and finds zero live references; if any
   reference is found, the WP fails.
6. **Structural tidy is checkable, not vibes.** After cleanup a repeat of the
   §Method unused-import scan reports **zero** unused imports/names over
   `backend/app/` + `backend/scripts/`, and any structural change (a moved,
   renamed or merged file) carries a removal-ledger-style `before → after` row in
   the WP2 CHANGELOG entry. If nothing was restructured this is trivially met
   (0 moves) — but "tidy for consistency" may not leave an unledgered move.
7. Deferred (documented, not run in-session): `cd backend && pytest` (full
   DB/API suite) on the user's machine confirms no import broke. Stated in the
   CHANGELOG.
8. A `CHANGELOG.md` entry for WP2 exists (with the removal ledger).

**Verifier checklist.** Re-run the in-session subset → counts match #2;
`py_compile` green (#3); `tsc --noEmit` 0 (#4); pick 3 removal-ledger rows and
independently grep for live references (must be zero, #5); re-run the
unused-import scan → **zero** and confirm any moved/renamed file carries a ledger
row (#6); confirm the "do NOT touch" list was respected (`git diff --stat` shows
those paths unchanged); confirm the deferred full-`pytest` runbook is stated;
confirm the CHANGELOG entry + ledger.

---

## WP3 — Scenario simulation engine (the main feature)

**Scope.** Per stock, a coherent set of scenarios with target valuations,
horizons, probabilities and a set-level probability-weighted EV — deterministic
core + an optional Claude-API refiner, both extending existing patterns.

### WP3a — Pure deterministic engine `services/scenarios.py`

Pure functions only (imports `insights`/`metrics`/`thesis`/`strategies` +
stdlib; **no** DB/framework/PyPI). Recomputes no indicator; every scenario
number is a pure function of sourced inputs and carries a **provenance label**.

**Dataclasses (`to_dict()` mirrors the API shape):**
- `ScenarioInputs` — wraps `thesis.ThesisInputs` and adds the valuation drivers
  the target math needs: `multiple_history` (own-history stats for the
  sector-relevant multiple — see below), `eps` (from `ttm.eps`), `book_value`
  (equity, tys. PLN, from the latest balance), `ebitda_ttm` (tys. PLN or None),
  `shares_outstanding`, `current_price` (`ttm.price`), `net_cash` (tys. PLN).
- `Scenario` — `id`, `kind ∈ {negative, base, positive, event}`, `label`
  (Polish), `probability` (float 0–1), `narrative` (Polish, sourced),
  `target_multiple: {type ∈ {cz,cwk,ev_ebitda}, value, basis_label}`,
  `target_price` (PLN | None), `implied_upside_pct` (float | None),
  `horizon: {low_months, high_months, basis_label}`, `drivers: list[str]`
  (each traceable), `assumptions: list[str]` (each **labelled** as an
  assumption).
- `ScenarioSet` — `scenarios: list[Scenario]`, `valuation_multiple: str`,
  `current_price`, `weighted_expected_price` (PLN | None),
  `weighted_expected_upside_pct` (float | None), `framing` (fixed Polish
  "punkt wejścia w analizę, nie sygnał"), `disclaimer` (= `thesis.DISCLAIMER`),
  `engine` ("deterministic" here; `scenarios_ai` may set "ai").

**Multiple selection (reuse strategy data — no new mapping).**
`select_valuation_multiple(sector_group, profile) -> "cz"|"cwk"|"ev_ebitda"`:
derive from the profile's `entry_rule.valuation` ∩ applicable criteria —
`finance`/`realestate` → `cwk`, `energy` → `ev_ebitda`, else → `cz`. (This is
exactly the `malik.py` applicability already encoded; do not hardcode a second
copy.)

**Own-multiple history (a real data gap to close).** Today `dossier.py` computes
`compute_pe_history` only for the `cz` indicator series. WP3 generalises this so
the **sector-relevant** multiple has an own-history range:
- Add a pure `metrics.compute_multiple_history(values, current)` (generalise the
  existing `compute_pe_history`; keep `compute_pe_history` as a thin alias so
  nothing breaks) → `{median, q1, q3, current, percentile, n}`.
- In `dossier.py`, load the history series for the selected multiple from
  `indicator_values` (the same query already used for `cz`, parametrised by
  indicator code: `cwk`/`ev_ebitda`) and pass it as `multiple_history`.
- When the series is empty or the per-share driver is missing (e.g. `ebitda_ttm`
  unavailable for an EV/EBITDA name), the engine **labels the gap** and falls
  back to `cz`; if `cz` is also unavailable, targets are `None` with a
  `verify_next`-style note — **never fabricated**.

**Target-price math (pure, unit-tested against hand-checked numbers):**
- `cz`: `target_price = target_pe × eps` (`eps` PLN).
- `cwk`: `target_price = target_pwk × bvps`, `bvps = book_value_tys × 1000 /
  shares`.
- `ev_ebitda`: `implied_ev = target_mult × ebitda_ttm_tys × 1000`;
  `implied_equity = implied_ev − net_debt_pln` (`net_debt_pln =
  −net_cash_tys × 1000`); `target_price = implied_equity / shares`.
- `implied_upside_pct = (target_price / current_price − 1) × 100`.
- `weighted_expected_price = Σ pᵢ · target_priceᵢ` over scenarios with a price;
  `weighted_expected_upside_pct` from that vs `current_price`.
- Money rules honoured: statements tys. PLN → ×1000 to PLN exactly where shown;
  price/mcap PLN; `pl-PL` formatting is the **frontend's** job (backend emits
  raw numbers, same as `ttm`).

**Deterministic scenario construction (no key / fallback).** Three
multiple-reversion scenarios off the own-history range:
- **negative** — multiple derates toward the own **Q1** (or historical low);
  earnings held flat. Probability **0.25**.
- **base** — multiple reverts toward the own **median**; earnings flat.
  Probability **0.50**.
- **positive** — multiple re-rates toward the own **Q3** (or historical high);
  earnings held flat. Probability **0.25**.
  (Exact split is a documented default → **Σ = 1.00** by construction; each
  scenario's `basis_label` names the quartile + the observation count, e.g.
  `"własna mediana C/Z 11,3 (n=8)"`.) **Event scenarios are NOT emitted by the
  deterministic engine** (it cannot invent catalysts) — they are an AI-only
  enrichment (WP3b); their absence with no key is honest.
- `horizon` default when the corpus lacks comparable durations: a **labelled**
  band (e.g. `low_months=12, high_months=24`, basis
  `"domyślny zakres — brak porównywalnych repricingów w korpusie"`). WP4's
  corpus enrichment lets `scenarios_ai` cite real durations.

**Entry point:** `build_scenario_set(inputs: ScenarioInputs, profile) ->
ScenarioSet`.

### WP3b — AI refiner `services/scenarios_ai.py` (extends `thesis_ai.py`)

`simulate_scenarios(inputs, profile, deterministic_set=None, *, ticker=None,
corpus=None, transport=None, settings=None) -> dict`. Same shape/decisions as
`refine_thesis`:
- **Reuse, don't duplicate.** Import from `thesis_ai`: `default_transport`,
  `collect_input_numbers`, and the JSON/number helpers. Where a needed helper is
  currently underscore-private (`_extract_json`, `_parse_response`, `_numbers`),
  add a **single-line public alias** in `thesis_ai.py` (no behaviour change) so
  it can be imported — `thesis_ai`'s 17 tests must stay green.
- **Bounded rounds** = `anthropic_max_iterations`. Each round sends: serialized
  `ScenarioInputs`, the active `StrategyProfile`, the `WorkedCase` corpus
  (comparables + their multiples/durations after WP4), and the current scenario
  set. The model may: **propose company-specific event scenarios** (grounded in
  the dossier's `insights`/`verify_next` gaps — catalyst, backlog, etc.),
  **re-word narratives**, and **adjust probabilities/horizons**, sanity-checking
  probability & timing against the historical multiple-reversion + comparables.
- **Coherence re-imposed by us (not trusted from the model):** after each round
  the engine **renormalises probabilities so Σ = 1** (divide by total; clamp
  each to [0,1]); a set failing `|Σ−1| ≤ 0.01` before renormalisation is a
  validation flag, not a crash.
- **Fabrication guard (the crux — wider allowed-set than the thesis).** Every
  number in the AI scenario output must be a subset of
  **`allowed = collect_input_numbers(inputs.thesis_inputs) ∪ corpus_numbers ∪
  engine_scenario_numbers`**, where `engine_scenario_numbers` are the numbers the
  **deterministic** engine computed (target prices, upsides, probabilities,
  horizons, weighted EV) and `corpus_numbers` are the labelled comparable
  figures from the corpus. A number outside that set → reject the round → fall
  back to the last valid set (else the deterministic set). This preserves
  "**every number traceable to fetched data, a labelled assumption, a
  deterministic computation, or a cited comparable**".
- **Early stop** on convergence (a round changes nothing) or on validation/
  transport failure. **Cache** JSON per `(ticker, input-hash, model, profile
  id+rules-hash)` under the gitignored `backend/.cache/scenarios_ai/`. **No-key
  fallback:** returns exactly `build_scenario_set(...).to_dict()` +
  `engine: "deterministic"`, never raises. `framing` + `DISCLAIMER` re-imposed
  every round.

### WP3c — Wiring + frontend

- `dossier.build_dossier` builds `ScenarioInputs`, calls
  `scenarios.build_scenario_set(...)` then `scenarios_ai.simulate_scenarios(...)`
  (transparent deterministic pass-through with no key) → new dossier
  **`scenarios`** block. `api/schemas.py` gains `ScenarioOut`/`ScenarioSetOut`
  nested in `DossierOut` (`scenarios: ScenarioSetOut`).
- Frontend `components/ScenariosPanel.tsx` on the Overview tab, **directly below
  `ThesisPanel`** (thesis = the read; scenarios = the projections off it). Order
  becomes MetricCards → Teza inwestycyjna → **Scenariusze** → Analiza spółki →
  Prescore → Kurs. Renders per scenario: label, probability, target price,
  implied upside, horizon; and set-level weighted-EV vs current price; an
  `"analiza — punkt wejścia, nie sygnał"` framing line; the `silnik:
  deterministyczny/AI` chip; the standing disclaimer. **Numeric fields**
  (target price, implied upside %, probability, weighted EV) — which the backend
  emits as **raw numbers, same as `ttm`** — are formatted through the project's
  `lib/format.ts` **pl-PL helpers** (`fmtPln`/`fmtPct`), exactly as
  `MetricCards`/`PriceChart` do (CLAUDE.md: "money formats pl-PL in UI"). The
  panel itself writes **no `toFixed`/`toLocaleString`/`Intl` literal** — all
  formatting is delegated to those centralised helpers. (Unlike `ThesisPanel`,
  which renders only backend-composed prose and so formats nothing; horizon
  months are small integers rendered as-is.)
- `src/lib/types.ts` gains `Scenario`/`ScenarioSet` mirroring the schema
  field-by-field; `Dossier.scenarios?` is **optional** (older cached dossiers
  degrade gracefully, same as `thesis?`).

**Acceptance (mechanically checkable).**
1. `scenarios.py` is pure (imports only `insights`/`metrics`/`thesis`/
   `strategies`/stdlib) and imports under system Python in-session;
   `scenarios_ai.py` imports with **no PyPI** (SDK/pydantic lazy — asserted:
   `anthropic`/`pydantic_settings` absent from `sys.modules` after import).
2. New `tests/test_scenarios.py` runs **green in-session** (plain asserts +
   `__main__` runner, like `test_thesis.py`), **≥ 9 tests**, covering by name:
   `test_target_price_cz_matches_hand_check`,
   `test_target_price_cwk_matches_hand_check`,
   `test_target_price_ev_ebitda_matches_hand_check`,
   `test_probabilities_sum_to_one`,
   `test_weighted_expected_value_matches_hand_check`,
   `test_multiple_selection_by_sector` (finance→cwk, energy→ev_ebitda, else→cz),
   `test_negative_base_positive_ordering` (upside neg ≤ base ≤ positive),
   `test_missing_driver_labels_gap_no_fabrication` (no `ebitda_ttm` → labelled
   gap / None target, **no invented number**),
   `test_every_scenario_number_is_traceable` (fabrication guard over the
   deterministic set: read-numbers ⊆ allowed-set). Hand-checked targets/upsides/
   weighted-EV are asserted to the exact rounded value.
3. New `tests/test_scenarios_ai.py` runs **green in-session** with a
   `StubTransport`, **≥ 10 tests**, covering by name at least: happy-path merge
   (`engine == "ai"`); malformed → clean deterministic fallback (no raise);
   iteration-limit (transport ≤ `max_iterations`); convergence (unchanged round
   stops early); **fabrication guard** — an out-of-allowed number is rejected;
   **corpus-number allowed** — a comparable figure from the injected corpus
   survives; **engine-number allowed** — a deterministic target/upside survives;
   **probability renormalisation** — after the model adds an event scenario the
   final Σ satisfies `|Σ−1| ≤ 0.01`; no-key deterministic fallback (== the
   deterministic set + marker, never raises); cache hit skips transport (one
   JSON file) + cache-disabled bypass; framing + `DISCLAIMER` preserved on the
   AI path.
4. `select_valuation_multiple` + the three target formulas match the spec's
   valuation doctrine (forward/own-history multiples) — a spot-check shows a
   scenario's own-history basis equals the dossier's `pe_history`/multiple stats
   (no divergence).
5. `dossier.py` + `schemas.py` **compile-check** in-session (`py_compile`);
   full `pytest`/DB path deferred (noted in CHANGELOG).
6. Frontend: `tsc --noEmit` **exits 0**; `types.ts` ↔ `ScenarioSetOut`
   field-by-field; `ScenariosPanel` formats numeric fields through the
   `lib/format.ts` pl-PL helpers (`fmtPln`/`fmtPct`) and writes **no
   `toFixed`/`toLocaleString`/`Intl` literal of its own** (grep-checked — the
   grep bars raw formatting *in the component*, not the centralised helpers),
   shows the framing + disclaimer + engine chip, and degrades when `scenarios`
   is absent. `npm run build`
   deferred to the user's machine (stated).
7. Money/format honoured (tys.→PLN ×1000 in the target math; reported mcap not
   re-derived; `pl-PL` only in the UI). Learning-note hook recorded for WP5.
8. Deferred real-call runbook documented (not run in-session):
   `cd backend && ANTHROPIC_API_KEY=… python scripts/scenarios_smoke.py SNT`
   (new script mirroring `thesis_ai_smoke.py`) prints `engine`, iteration count,
   the scenario set + weighted EV.

**Verifier checklist.** Re-run `test_scenarios.py` + `test_scenarios_ai.py`
in-session → green at the stated counts; hand-recompute one `cz`, one `cwk` and
one `ev_ebitda` target from the fixture inputs and confirm the engine matches;
confirm Σ probability = 1 on the deterministic set and `|Σ−1|≤0.01` after an
AI-added event scenario; grep `scenarios.py` for any literal target/upside not
derived from inputs (must be none); confirm the corpus/engine numbers are inside
the AI allowed-set while a scripted stray number is rejected; grep
`scenarios_ai.py` to confirm the SDK import is lazy and no key literal; confirm
`ScenariosPanel` formats via `lib/format.ts` pl-PL helpers (no raw
`toFixed`/`toLocaleString`/`Intl` literal in the component) + framing +
disclaimer + degraded branch;
`py_compile` `dossier.py`/`schemas.py`; confirm the smoke script + CHANGELOG
entry.

---

## WP4 — AI valuation agent + WorkedCase corpus enrichment

**Scope.** An API-agent step that takes **all gathered data + the WP3 scenarios**
and produces a **stock-potential valuation**; plus enriching the WorkedCase
corpus with real multiples/repricing durations (so scenarios' horizons and the
agent's confidence are evidence-based) **including at least one documented miss**
(survivorship-bias guard).

### WP4a — `services/valuation_ai.py` (extends `thesis_ai.py`)

`assess_potential(inputs, scenario_set, profile, *, ticker=None, corpus=None,
transport=None, settings=None) -> dict`. Produces a `valuation` block:
- `potential: {value_pct | range_pct, basis_label}` — how much upside potential,
  anchored to the scenario set's probability-weighted EV (deterministic
  fallback: `potential = weighted_expected_upside_pct`, `basis_label` naming it).
- `confidence: {level ∈ {low, medium, high}, rationale}` — a **deterministic
  heuristic with explicit, mechanically-checkable thresholds** keyed on data
  coverage = the count of computable **key indicators** (the thesis `computable`;
  `min_key_indicators=3`) and own-history depth (`multiple_history.n` from
  `compute_multiple_history`): **< 3** key indicators (`thesis.insufficient_data`)
  **or** empty own-history (`n == 0`) ⇒ `low`; **≥ 5** key indicators **AND**
  `n ≥ 4` (enough observations for a stable median/quartiles) ⇒ `high`;
  everything between — 3–4 key indicators, **or** ≥ 5 but `n < 4` ⇒ `medium`.
  The AI may re-word the rationale but the number-bearing facts (the counts and
  the resulting level) stay sourced.
- `what_would_change: list[{id, text, why}]` — what would move the assessment
  (derived from `thesis.verify_next` gaps + the scenario drivers). Never empty
  when gaps exist.
- `narrative` (Polish, sourced), `framing`, `disclaimer` (= `thesis.DISCLAIMER`),
  `engine`, and AI-path `ai_notes` (model, iterations, per-change rationale,
  case-similarity).
- **Same guard-rails as WP3b:** bounded rounds, cache
  (`backend/.cache/valuation_ai/`), the **fabrication guard** (numbers ⊆
  `inputs ∪ scenario_set ∪ corpus`), deterministic no-key fallback (never
  raises), lazy SDK import. Reuse `thesis_ai`'s transport/JSON/number helpers.

### WP4b — Enrich the WorkedCase corpus (`services/strategies/cases.py`)

- Add real, **sourced** multiples + **repricing durations** to comparison cases,
  each number carrying a `sources[...]` provenance label and a `citation`. The
  **DGN** catch gets whatever is honestly reconstructable (its verified POS-flag
  timeline + "+2500%/5y" framing — the "~20 PLN" entry stays **unverified /
  unused** per `docs/strategy-malik.md §Unverified`). Add **≥ 1 documented
  miss** — a stock that looked cheap on its own-history multiple but did **not**
  reprice (or kept derating) — with sourced numbers and an explicit "miss"
  label, so the corpus is not survivorship-biased.
- **Honesty rules unchanged:** no number without a source; where entry-era
  fundamentals aren't reconstructable in-sandbox, the field stays a labelled gap
  and the live reconstruction is deferred to `scripts/validate_thesis.py` on the
  user's machine. Preserve the **lazy `CORPUS`** pattern (PEP 562
  `__getattr__`) + import purity (the circular-import fix must survive).
- Corpus numbers are now inside the WP3b/WP4a fabrication **allowed-set**
  (`corpus_numbers`), so a scenario/valuation may legitimately cite a
  comparable's multiple or repricing duration — traceable, not fabricated.

### WP4c — Wiring + frontend

- `dossier.build_dossier` calls `valuation_ai.assess_potential(...)` after the
  scenarios → new dossier **`valuation`** block; `schemas.py` gains
  `ValuationOut` in `DossierOut`.
- `ScenariosPanel.tsx` (or a small sibling) renders the valuation:
  potential %/range, confidence level + rationale, "co zmieniłoby ocenę" list,
  framing, engine chip, disclaimer. `types.ts` gains `Valuation`;
  `Dossier.valuation?` optional.

**Acceptance (mechanically checkable).**
1. `valuation_ai.py` imports with **no PyPI** (SDK/pydantic lazy — asserted).
2. New `tests/test_valuation_ai.py` runs **green in-session** (StubTransport,
   **≥ 8 tests**): happy-path (`engine=="ai"`, `potential`/`confidence`/
   `what_would_change` present); no-key deterministic fallback (== the
   deterministic valuation + marker, `potential == scenario_set
   weighted_expected_upside_pct`, never raises); **fabrication guard** (a number
   outside `inputs ∪ scenarios ∪ corpus` rejected); scenario-number + corpus-
   number allowed; iteration-limit; convergence; cache hit/skip; framing +
   `DISCLAIMER` preserved.
3. `evaluate_case` (existing) runs on the **enriched** DGN/comparable/miss cases;
   a new `test` asserts the corpus loads lazily, is import-pure, contains
   **≥ 1 case tagged as a miss**, and that **every numeric field carries a
   `sources` label** (no bare number). `test_thesis_ai.py`'s corpus-dependent
   tests stay green (17/17) — the non-empty default `CORPUS` contract is
   unchanged.
4. Deterministic confidence heuristic is checkable **at the named thresholds**:
   an `insufficient_data` input (< 3 key indicators) → `confidence.level ==
   "low"`; a mid-coverage input (3–4 key indicators, **or** ≥ 5 with
   `multiple_history.n < 4`) → `== "medium"`; a full-coverage input (**≥ 5** key
   indicators **AND** `multiple_history.n ≥ 4`) → `== "high"` (each asserted).
5. `dossier.py`/`schemas.py` compile-check; frontend `tsc --noEmit` 0;
   `types.ts` ↔ `ValuationOut` field-by-field; `valuation` degrades gracefully
   when absent.
6. Deferred (documented): the real-key smoke (`scripts/scenarios_smoke.py`
   already prints the valuation block, or extend it) and full `pytest`/DB path.
7. `CHANGELOG.md` entry for WP4 (incl. the corpus sources + the "miss" case).

**Verifier checklist.** Re-run `test_valuation_ai.py` green; confirm the no-key
`potential` equals the scenario weighted upside; confirm the guard rejects a
stray number while a scenario/corpus number survives; confirm the confidence
heuristic returns `low`/`medium`/`high` at the named thresholds — a `medium`
case sits at the boundary (3–4 key indicators, or ≥ 5 with `multiple_history.n <
4`); open `cases.py` and confirm every added number has a `sources` entry + a
`citation`, the miss case is present and labelled, and `CORPUS` is still
lazy/import-pure (grep for the `__getattr__` + no eager build); confirm
`test_thesis_ai.py` still 17/17;
`py_compile` + `tsc`; confirm the CHANGELOG entry.

---

## WP5 — Testing, honest verdict, memory/changelog

**Scope.** Run every in-session-runnable test; state exact counts; give an honest
verdict on what verifiably works vs what needs the user's machine; then compact
memory + write the learning note.

**Deliverables.**
- **`docs/validation-scenarios.md`** — fixture-first validation of the scenario
  + valuation engines (mirror `docs/validation-thesis.md`): per fixture ticker,
  the deterministic scenario set with **hand-checked target/upside/EV numbers**,
  a probability-coherence check, the multiple-selection-by-sector check, and an
  explicit **gaps** subsection. Any live BR probe is **fixture-first**, ≤ a few
  polite `web_fetch` requests with replicated politeness, **no archiwum
  pagination**, quirks followed not re-derived — or explicitly deferred with the
  precise reason (as in the thesis validation).
- **Exact test counts** for the whole in-session-runnable suite (pure subset +
  pytest-shim subset), each new test file's count named, plus the honest list of
  what needs the user's machine: `cd backend && pytest` (full DB/API),
  `cd frontend && npm run build`, `ANTHROPIC_API_KEY=… python
  scripts/scenarios_smoke.py <TICKER>` (real refinement), and
  `scripts/validate_thesis.py`/live BR (egress).
- **`docs/learning/phase-scenarios.md`** (≤ 1 page): what was built, 3–5
  concepts, C# analogies (e.g. scenario set ≈ a strategy-pattern projector
  returning a small result collection; the AI agents ≈ a decorator over pure
  compute with an injected transport + a validation guard, like the thesis
  refiner; probability renormalisation ≈ normalising weights before a weighted
  average), where to look in the code.
- **CLAUDE.md** on-demand index updated to list `docs/plan-stage-scenarios.md`,
  `docs/validation-scenarios.md`, `docs/learning/phase-scenarios.md`.
- **CHANGELOG.md** final stage-closeout entry (date · scope · what + why ·
  decisions); per-WP entries already exist. **TASKS.md** SC boxes ticked only
  now (after the final conformance review).

**Acceptance (mechanically checkable).**
1. In-session test subset green with **named exact counts**, incl. the new
   `test_scenarios.py` / `test_scenarios_ai.py` / `test_valuation_ai.py`; the
   stage-TH baseline (thesis 13, thesis_ai 17, metrics 20, insights 15, …) is
   **not regressed**.
2. `docs/validation-scenarios.md` present with hand-checked numbers + an explicit
   gaps/deferred subsection (nothing papered over); politeness note (archiwum
   untouched, 0 pagination, quirks followed).
3. `docs/learning/phase-scenarios.md` present with C# analogies; CLAUDE.md index
   references the three new docs; final CHANGELOG entry present; TASKS.md SC
   ticked.
4. A fresh-context reader can, from **this file alone**, tell for each WP whether
   it passed.

**Verifier checklist.** Run the in-session subset and confirm the counts in the
doc; open `docs/validation-scenarios.md` and re-check a sample of the hand-checked
numbers against the fixture; confirm the CLAUDE.md index + learning note + final
CHANGELOG entry + TASKS.md ticks; re-read each WP's acceptance and tick it against
the delivered artifacts.

---

## Risks & honesty rules (binding)

- **Missing driver ≠ invented target.** If the sector multiple's per-share driver
  (EBITDA TTM, book value, EPS) isn't computable, the scenario **labels the gap**
  and yields a `None` target (routed to a verify note) — never a guessed price.
  The fabrication guard (`test_scenarios*`) enforces it.
- **Every number traceable.** A scenario/valuation number must be sourced from
  fetched inputs, a **labelled** assumption, a **deterministic computation** from
  those, or a **cited** worked-case comparable. The AI path is held to the same
  allowed-set as the deterministic path — a stray figure rejects the round.
- **Probabilities stay coherent.** Σ = 1 by construction deterministically;
  re-normalised (and asserted `|Σ−1| ≤ 0.01`) whenever the AI adds/edits
  scenarios.
- **Not investment advice.** Standing `DISCLAIMER` + "punkt wejścia, nie sygnał"
  framing on every scenario set and valuation. Upsides are conditional
  projections, never targets to act on.
- **No survivorship bias.** The corpus carries **≥ 1 documented miss**; horizons
  cite real repricing durations, not just the wins.
- **Deterministic-first.** The AI agents are never on the critical path: no key
  ⇒ the deterministic scenario set + a weighted-EV-anchored valuation, and the
  dossier always has both blocks.
- **Scraping stays polite.** No new sources; archiwum page 1 only; quirks from
  the ledger, not re-derived; validation fixture-first.
- **Simple first.** Discrete scenarios, not Monte-Carlo; strategy stays data;
  reuse `thesis_ai`/`insights`/`metrics`/`compute_pe_history` rather than
  re-implement. The only new "config surface" is the two cache dirs +
  the reused `anthropic_*` settings.

## Verification protocol (per WP)

For each WP a **fresh-context sonnet verifier** checks the implementation against
**this document's** acceptance criteria and must collect concrete evidence:

- **Re-run the named in-session tests** and record pass/fail counts (never trust
  a prose claim of green).
- **Independently re-derive** at least one number the WP asserts (a target price,
  a weighted EV, a probability sum, an archived-changelog byte-diff, a
  zero-reference grep) — the verifier reproduces it, not just reads it.
- **Grep for fabrication / divergence:** no scenario number outside the
  allowed-set; no strategy literal in the generic engine; no raw
  `toFixed`/`toLocaleString`/`Intl` literal on the panel (the `lib/format.ts`
  pl-PL helpers are the project convention for numeric fields); no key literal
  in the AI modules; SDK imports lazy.
- **Confirm honesty deferrals are explicit** (DB/API `pytest`, `npm run build`,
  real-key smoke, live BR) — deferred, not silently skipped.
- **Confirm a CHANGELOG entry** exists for the WP.
- A WP is **done only on a verifier PASS**; fail → fix → re-verify. WP5 is the
  stage-level plan-conformance review.

**Model split (binding):** implementation = **opus**; verification/testing =
**sonnet**; planning/orchestration = top-level session.

## Reconciliation with Phase 5

Like TH.2b, WP3/WP4 are **engine-level, deterministic-first Claude-API
enrichments of the dossier** (`scenarios` + `valuation` blocks). They do **not**
deliver the Phase-5 analysis product: `skill/SKILL.md` + `rubric.md` +
`examples/` (P5.1–P5.3), the `analyses` table + `POST/GET .../analyses` +
**Analiza AI** tab + `AI_DAILY_LIMIT` (P5.6/P5.7), and the forum distiller
(P5.9) stay Phase 5. What **shrinks**: `scenarios_ai.py`/`valuation_ai.py` reuse
TH.2b's transport/config/cache, so **P5.4 `claude_client.py` builds on the same
transport** rather than starting fresh. Recorded in TASKS.md Phase-5 intro — the
P5 tasks are **not** rewritten.

## Stage tasks

Tracked in `TASKS.md` under **Stage SC — Scenario simulation engine** (IDs
`SC.1`–`SC.5`, stable for referencing in sessions, e.g. "do SC.3"). Added in
WP1; ticked only after each WP's verifier PASS.
